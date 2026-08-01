#include "sha1.h"

#include <cstdint>
#include <cstdio>
#include <fstream>
#include <string>
#include <vector>

namespace {

constexpr const char* kDefaultRom = "Metroid Prime Hunters.nds";
constexpr const char* kExpectedSha1 =
    "90164d1ac127ee5f9815ea4ae7de798c7b5fc629";
constexpr const char* kExpectedTitle = "MP HUNTERS";
constexpr const char* kExpectedGameCode = "AMHE";
constexpr std::size_t kExpectedSize = 64u * 1024u * 1024u;

std::vector<uint8_t> read_file(const std::string& path) {
    std::ifstream file(path, std::ios::binary | std::ios::ate);
    if (!file) return {};
    const std::streamsize size = file.tellg();
    if (size <= 0) return {};
    file.seekg(0, std::ios::beg);
    std::vector<uint8_t> bytes(static_cast<std::size_t>(size));
    if (!file.read(reinterpret_cast<char*>(bytes.data()), size)) return {};
    return bytes;
}

std::string ascii_field(const std::vector<uint8_t>& rom,
                        std::size_t offset, std::size_t size) {
    std::string value(reinterpret_cast<const char*>(rom.data() + offset), size);
    while (!value.empty() && (value.back() == '\0' || value.back() == ' '))
        value.pop_back();
    return value;
}

uint32_t read_u32(const std::vector<uint8_t>& rom, std::size_t offset) {
    return static_cast<uint32_t>(rom[offset])
         | (static_cast<uint32_t>(rom[offset + 1]) << 8)
         | (static_cast<uint32_t>(rom[offset + 2]) << 16)
         | (static_cast<uint32_t>(rom[offset + 3]) << 24);
}

void usage(const char* executable) {
    std::fprintf(stderr, "usage: %s [--rom <path>]\n", executable);
}

}  // namespace

int main(int argc, char** argv) {
    std::string rom_path = kDefaultRom;
    for (int i = 1; i < argc; ++i) {
        const std::string argument = argv[i];
        if (argument == "--help" || argument == "-h") {
            usage(argv[0]);
            return 0;
        }
        if (argument == "--rom" && i + 1 < argc) {
            rom_path = argv[++i];
            continue;
        }
        std::fprintf(stderr, "unknown or incomplete argument: %s\n",
                     argument.c_str());
        usage(argv[0]);
        return 2;
    }

    const std::vector<uint8_t> rom = read_file(rom_path);
    if (rom.size() < 0x200u) {
        std::fprintf(stderr, "unable to read an NDS header from: %s\n",
                     rom_path.c_str());
        return 1;
    }

    const std::string title = ascii_field(rom, 0x00u, 12u);
    const std::string game_code = ascii_field(rom, 0x0Cu, 4u);
    const unsigned revision = rom[0x1Cu];
    const std::string digest = gba::sha1(rom.data(), rom.size()).hex();

    bool valid = true;
    if (rom.size() != kExpectedSize) {
        std::fprintf(stderr, "ROM size mismatch: got %zu, expected %zu\n",
                     rom.size(), kExpectedSize);
        valid = false;
    }
    if (title != kExpectedTitle || game_code != kExpectedGameCode ||
        revision != 0u) {
        std::fprintf(stderr,
            "ROM identity mismatch: title=%s code=%s revision=%u\n",
            title.c_str(), game_code.c_str(), revision);
        valid = false;
    }
    if (digest != kExpectedSha1) {
        std::fprintf(stderr, "ROM SHA-1 mismatch: got %s, expected %s\n",
                     digest.c_str(), kExpectedSha1);
        valid = false;
    }
    if (!valid) {
        std::fputs("refusing selection: this project is pinned to AMHE0\n",
                   stderr);
        return 1;
    }

    std::puts("selection=metroid-prime-hunters");
    std::printf("rom=%s\n", rom_path.c_str());
    std::printf("title=%s game_code=%s revision=%u sha1=%s\n",
                title.c_str(), game_code.c_str(), revision, digest.c_str());
    std::printf("arm9_entry=0x%08x arm7_entry=0x%08x\n",
                read_u32(rom, 0x24u), read_u32(rom, 0x34u));
    std::printf("arm9_size=0x%08x arm7_size=0x%08x\n",
                read_u32(rom, 0x2Cu), read_u32(rom, 0x3Cu));
    std::puts("reference=NoneGiven/MphRead (AMHE0-aware; non-matching recreation)");
    std::puts("boot_status=authentic-firmware-and-cartridge");
    std::puts("attract_status=full-no-input-loop");
    return 0;
}
