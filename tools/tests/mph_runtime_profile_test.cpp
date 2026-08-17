#include <array>
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
    std::array<uint8_t, 4> crc_suffix;
    uint32_t morph;
    uint32_t aim_x;
    uint32_t aim_y;
};

// Each synthetic ROM uses a 0-byte ARM9 and a 4-byte ARM7. The four suffix
// bytes were solved so melonPrimeDS's CRC32(header[0:0x40], ARM9, ARM7)
// equals the canonical checksum for the corresponding retail profile. This
// tests the real detector without shipping or reading copyrighted ROM data.
constexpr RuntimeCase kCases[] = {
    {"US1_0", "AMHE", 0, {0x45, 0x3D, 0xE6, 0x16}, 0x020DA818u, 0x020DE526u, 0x020DE52Eu},
    {"US1_1", "AMHE", 1, {0xE0, 0xF3, 0x6E, 0x2A}, 0x020DB098u, 0x020DEDA6u, 0x020DEDAEu},
    {"EU1_0", "AMHP", 0, {0x66, 0x59, 0x8A, 0xC0}, 0x020DB0B8u, 0x020DEDC6u, 0x020DEDCEu},
    {"EU1_1", "AMHP", 1, {0x7B, 0xD4, 0x8E, 0xCB}, 0x020DB138u, 0x020DEE46u, 0x020DEE4Eu},
    {"JP1_0", "AMHJ", 0, {0xF0, 0x91, 0x6F, 0xD1}, 0x020DC6D8u, 0x020E03E6u, 0x020E03EEu},
    {"JP1_1", "AMHJ", 1, {0x89, 0x6F, 0x91, 0xF1}, 0x020DC698u, 0x020E03A6u, 0x020E03AEu},
    {"KR1_0", "AMHK", 0, {0x4C, 0xE9, 0x78, 0xBD}, 0x020D3EE4u, 0x020D7C0Eu, 0x020D7C16u},
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

void write_le32(std::vector<uint8_t>& rom, std::size_t offset, uint32_t value) {
    rom[offset + 0] = static_cast<uint8_t>(value >> 0);
    rom[offset + 1] = static_cast<uint8_t>(value >> 8);
    rom[offset + 2] = static_cast<uint8_t>(value >> 16);
    rom[offset + 3] = static_cast<uint8_t>(value >> 24);
}

std::vector<uint8_t> make_rom(
    const char* game_code, uint8_t revision, std::array<uint8_t, 4> suffix) {
    std::vector<uint8_t> rom(0x44u, 0u);
    std::memcpy(rom.data() + 0x0Cu, game_code, 4u);
    rom[0x1Eu] = revision;
    write_le32(rom, 0x20u, 0x40u);  // ARM9 ROM offset
    write_le32(rom, 0x2Cu, 0u);     // ARM9 size
    write_le32(rom, 0x30u, 0x40u);  // ARM7 ROM offset
    write_le32(rom, 0x3Cu, 4u);     // ARM7 size
    std::memcpy(rom.data() + 0x40u, suffix.data(), suffix.size());
    return rom;
}

bool select_rom(
    const std::vector<uint8_t>& rom,
    const char* actual_sha1 = kUnknownSha1,
    const char* expected_sha1 = "") {
    return nds_title_patches_select_mph_runtime_profile(
        rom.data(), static_cast<uint64_t>(rom.size()),
        actual_sha1, expected_sha1);
}

}  // namespace

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
    for (const RuntimeCase& c : kCases) {
        const auto rom = make_rom(c.game_code, c.revision, c.crc_suffix);
        expect(select_rom(rom), c.name);
        expect(nds_title_patches_mph_host_writes_compatible(),
               "canonical executable checksum must authorize host writes");

        g_writes.clear();
        expect(!nds_title_patches_apply_mph_mouse_delta(7, -5),
               "profile switch must clear direct-aim enable state");
        nds_title_patches_set_mph_mouse_aim(true);
        expect(nds_title_patches_apply_mph_mouse_delta(7, -5),
               "authoritative checksum must accept direct mouse aim");
        expect(g_writes.size() == 2,
               "recognized profile must perform two aim writes");
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

    // Whole-ROM SHA mismatch is allowed only when a clean build sees the same
    // canonical executable checksum. This supports data-only variants without
    // reusing a clean build for code-modified content.
    const auto us10 = make_rom("AMHE", 0, {0x45, 0x3D, 0xE6, 0x16});
    expect(select_rom(us10, kUnknownSha1, kUs10Sha1),
           "US1.0 canonical executable variant must select");
    expect(nds_title_patches_mph_allows_rom_sha1_mismatch(),
           "canonical US1.0 executable may reuse US1.0 clean build");

    const auto eu11 = make_rom("AMHP", 1, {0x7B, 0xD4, 0x8E, 0xCB});
    expect(select_rom(eu11, kUnknownSha1, kUs10Sha1),
           "EU1.1 canonical executable must still identify EU1.1 base");
    expect(!nds_title_patches_mph_allows_rom_sha1_mismatch(),
           "EU1.1 executable must never bypass a US1.0 clean SHA gate");

    // melonPrimeDS explicitly recognizes this EU1.1 Russian variant checksum,
    // so its RAM layout is authoritative and host writes are safe. However its
    // executable checksum is not the canonical clean EU1.1 checksum, therefore
    // it still needs its own exact mod-specific recomp build/capture identity.
    const auto eu11_russian =
        make_rom("AMHP", 1, {0xCE, 0x58, 0x0D, 0xA4});  // 0x9E20F3A8
    expect(select_rom(eu11_russian, kUnknownSha1, kEu11Sha1),
           "known EU1.1 Russian executable must identify EU1.1 base");
    expect(nds_title_patches_mph_host_writes_compatible(),
           "known EU1.1 Russian checksum must authorize its address table");
    expect(!nds_title_patches_mph_allows_rom_sha1_mismatch(),
           "code-modified known variant must not reuse clean EU1.1 build");

    // Unknown checksum with a valid header is only a candidate base profile.
    // It may be reported/routed as that base, but dangerous host RAM accesses
    // remain disabled until its executable checksum is explicitly validated.
    const auto unknown_us10 = make_rom("AMHE", 0, {0, 0, 0, 0});
    expect(select_rom(unknown_us10),
           "unknown checksum with supported header should identify a candidate base");
    expect(!nds_title_patches_mph_host_writes_compatible(),
           "header fallback alone must not authorize host writes");
    g_writes.clear();
    nds_title_patches_set_mph_mouse_aim(true);
    expect(!nds_title_patches_apply_mph_mouse_delta(1, 1),
           "unknown executable checksum must reject direct mouse writes");
    expect(g_writes.empty(),
           "unknown executable checksum must not touch profile RAM");
    g_morph_addr = 0x020DA818u;
    g_morph_value = 0x02u;
    expect(!nds_title_patches_mph_in_ball(),
           "unknown executable checksum must reject morph-state host read");
    expect(!nds_title_patches_mph_allows_rom_sha1_mismatch(),
           "unknown executable checksum must not bypass clean SHA gate");

    // Exact clean whole-ROM SHA cannot contradict the selected executable base.
    expect(!select_rom(eu11, kUs10Sha1, ""),
           "known-clean US1.0 SHA with EU1.1 executable must fail closed");
    expect(!select_rom(us10, kEu11Sha1, ""),
           "known-clean EU1.1 SHA with US1.0 executable must fail closed");

    // Unsupported headers/revisions and malformed binary ranges fail closed.
    const auto unknown_code = make_rom("ZZZZ", 0, {0, 0, 0, 0});
    expect(!select_rom(unknown_code), "unknown game code must fail closed");
    const auto rev2 = make_rom("AMHE", 2, {0, 0, 0, 0});
    expect(!select_rom(rev2), "unknown USA revision must fail closed");
    const auto kr_rev1 = make_rom("AMHK", 1, {0, 0, 0, 0});
    expect(!select_rom(kr_rev1), "unknown Korea revision must fail closed");

    auto bad_range = make_rom("AMHE", 0, {0, 0, 0, 0});
    write_le32(bad_range, 0x20u, 0xFFFFFFF0u);
    write_le32(bad_range, 0x2Cu, 0x100u);
    expect(!select_rom(bad_range), "out-of-range ARM9 image must fail closed");

    std::vector<uint8_t> tiny(0x1Eu, 0u);
    expect(!nds_title_patches_select_mph_runtime_profile(
               tiny.data(), static_cast<uint64_t>(tiny.size()),
               kUnknownSha1, ""),
           "truncated NDS header must fail closed");
    expect(!nds_title_patches_select_mph_runtime_profile(
               us10.data(), static_cast<uint64_t>(us10.size()),
               nullptr, ""),
           "missing actual-content identity must fail closed");

    if (g_failures != 0) {
        std::fprintf(stderr, "%d runtime-profile assertion(s) failed\n",
                     g_failures);
        return 1;
    }
    std::puts(
        "OK: seven MPH base profiles use melonPrimeDS executable CRC; "
        "header fallback and whole-ROM provenance gates fail closed");
    return 0;
}
