#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

#include "state.h"
#include "title_patches.h"

namespace {

struct Write32 {
    uint32_t addr;
    uint32_t value;
};

struct RuntimeCase {
    const char* name;
    const char* game_code;
    uint8_t revision;
    uint32_t morph;
    uint32_t aim_x;
    uint32_t aim_y;
};

constexpr RuntimeCase kCases[] = {
    {"US1_0", "AMHE", 0, 0x020DA818u, 0x020DE526u, 0x020DE52Eu},
    {"US1_1", "AMHE", 1, 0x020DB098u, 0x020DEDA6u, 0x020DEDAEu},
    {"EU1_0", "AMHP", 0, 0x020DB0B8u, 0x020DEDC6u, 0x020DEDCEu},
    {"EU1_1", "AMHP", 1, 0x020DB138u, 0x020DEE46u, 0x020DEE4Eu},
    {"JP1_0", "AMHJ", 0, 0x020DC6D8u, 0x020E03E6u, 0x020E03EEu},
    {"JP1_1", "AMHJ", 1, 0x020DC698u, 0x020E03A6u, 0x020E03AEu},
    {"KR1_0", "AMHK", 0, 0x020D3EE4u, 0x020D7C0Eu, 0x020D7C16u},
};

constexpr const char* kUs10Sha1 =
    "90164d1ac127ee5f9815ea4ae7de798c7b5fc629";
constexpr const char* kEu11Sha1 =
    "bdcd1dea293e24c98d4c481430e90d21198985a5";
constexpr const char* kUnknownSha1 =
    "0000000000000000000000000000000000000000";

std::vector<Write32> g_writes;
uint32_t g_morph_addr = 0;
uint8_t g_morph_value = 0;
int g_failures = 0;

void expect(bool condition, const char* message) {
    if (condition) return;
    std::fprintf(stderr, "FAIL: %s\n", message);
    ++g_failures;
}

void expect_write(std::size_t index, uint32_t addr, uint32_t value,
                  const char* message) {
    const bool ok = index < g_writes.size() &&
                    g_writes[index].addr == addr &&
                    g_writes[index].value == value;
    expect(ok, message);
}

std::vector<uint8_t> make_rom(const char* game_code, uint8_t revision) {
    std::vector<uint8_t> rom(0x200u, 0u);
    std::memcpy(rom.data() + 0x0Cu, game_code, 4u);
    rom[0x1Eu] = revision;
    return rom;
}

bool select(const char* game_code, uint8_t revision, const char* sha1) {
    const auto rom = make_rom(game_code, revision);
    return nds_title_patches_select_mph_runtime_profile(
        rom.data(), static_cast<uint64_t>(rom.size()), sha1);
}

}  // namespace

// title_patches.cpp only needs these bus surfaces. Keeping the test at the
// ABI boundary lets it link the real patched translation unit without a ROM,
// BIOS dump, or generated recomp bank.
bool bus_get_region(const char*, BusRegion*) {
    return false;
}

extern "C" uint8_t bus_read_u8_slow(uint32_t addr) {
    return addr == g_morph_addr ? g_morph_value : 0u;
}

extern "C" void bus_write_u32_slow(uint32_t addr, uint32_t value) {
    g_writes.push_back({addr, value});
}

int main() {
    // All seven retail base profiles must dispatch from gameCode@0x0C plus the
    // exact supported revision@0x1E even when the whole-ROM SHA-1 is unknown.
    // This is the mod-ROM path: content identity is provenance, not selector.
    for (const RuntimeCase& c : kCases) {
        expect(select(c.game_code, c.revision, kUnknownSha1), c.name);

        // Profile selection clears the previous direct-aim enable state.
        g_writes.clear();
        expect(!nds_title_patches_apply_mph_mouse_delta(7, -5),
               "profile switch must clear direct-aim enable state");
        expect(g_writes.empty(),
               "disabled aim after profile switch must not write");

        nds_title_patches_set_mph_mouse_aim(true);
        expect(nds_title_patches_apply_mph_mouse_delta(7, -5),
               "recognized base profile must accept direct mouse aim");
        expect(g_writes.size() == 2,
               "recognized base profile must perform two aim writes");
        expect_write(0, c.aim_x, 7u,
                     "X delta must target profile-specific baseAimX");
        expect_write(1, c.aim_y, static_cast<uint32_t>(-5),
                     "Y delta must target profile-specific baseAimY");

        g_morph_addr = c.morph;
        g_morph_value = 0x02u;
        expect(nds_title_patches_mph_in_ball(),
               "baseIsAltForm=2 must report Morph Ball");
        g_morph_value = 0x00u;
        expect(!nds_title_patches_mph_in_ball(),
               "non-alt form must not report Morph Ball");
    }

    // Known-clean SHA-1 is consistency/provenance only. Matching clean
    // identities work, but a clean hash paired with a contradictory header is
    // impossible and must fail closed instead of trusting either side.
    expect(select("AMHE", 0, kUs10Sha1),
           "known-clean US1.0 must match its header profile");
    expect(select("AMHP", 1, kEu11Sha1),
           "known-clean EU1.1 must match its header profile");
    expect(!select("AMHP", 1, kUs10Sha1),
           "known-clean US1.0 SHA with EU1.1 header must fail closed");
    expect(!select("AMHE", 0, kEu11Sha1),
           "known-clean EU1.1 SHA with US1.0 header must fail closed");

    // Unknown/ambiguous identities must never be guessed as US1.0. Revisions
    // other than the explicitly supported 0/1 set are rejected; KR only has
    // revision 0 in the seven-profile table.
    expect(!select("ZZZZ", 0, kUnknownSha1),
           "unknown game code must fail closed");
    expect(!select("AMHE", 2, kUnknownSha1),
           "unknown USA revision must fail closed");
    expect(!select("AMHP", 2, kUnknownSha1),
           "unknown Europe revision must fail closed");
    expect(!select("AMHJ", 2, kUnknownSha1),
           "unknown Japan revision must fail closed");
    expect(!select("AMHK", 1, kUnknownSha1),
           "unknown Korea revision must fail closed");

    std::vector<uint8_t> tiny(0x1Eu, 0u);
    expect(!nds_title_patches_select_mph_runtime_profile(
               tiny.data(), static_cast<uint64_t>(tiny.size()), kUnknownSha1),
           "truncated NDS header must fail closed");
    const auto valid = make_rom("AMHE", 0);
    expect(!nds_title_patches_select_mph_runtime_profile(
               valid.data(), static_cast<uint64_t>(valid.size()), nullptr),
           "missing actual-content identity must fail closed");

    // Failed selection clears the prior profile so stale addresses cannot
    // remain active after a cartridge/identity change.
    g_writes.clear();
    nds_title_patches_set_mph_mouse_aim(true);
    expect(!nds_title_patches_apply_mph_mouse_delta(9, 9),
           "failed selection must reject mouse aim");
    expect(g_writes.empty(),
           "failed selection must not retain prior profile writes");
    expect(!nds_title_patches_mph_in_ball(),
           "failed selection must not retain prior morph address");

    if (g_failures != 0) {
        std::fprintf(stderr, "%d runtime-profile assertion(s) failed\n",
                     g_failures);
        return 1;
    }
    std::puts(
        "OK: header-based MPH runtime profiles dispatch all seven revisions; "
        "SHA-1 remains provenance");
    return 0;
}
