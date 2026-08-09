/**
 * k0_ros_determinism_standalone.cpp
 * ---------------------------------
 * Standalone (zero ROS dependency) determinism test for the ROS 2 K0-Lite node.
 *
 * It reuses VERBATIM the k0lite + sha256 + k0_determinism_run logic from
 * ros2/k0_snn_controller/src/k0_snn_node.cpp (the `determinism_test` mode), so the
 * hash produced here is exactly the hash the ROS 2 node prints in
 * AX_K0_LITE_ROS2_DETERMINISM_TEST. This lets the determinism property be verified
 * and recorded WITHOUT a ROS 2 Jazzy / rclcpp toolchain (unavailable off-Pi).
 *
 * Build : g++ -O2 -std=c++17 k0_ros_determinism_standalone.cpp -o k0_ros_det
 * Run   : ./k0_ros_det   ->  prints run1, run2, PASS, and the JSON line.
 */

#include <cstdint>
#include <cstring>
#include <array>
#include <vector>
#include <string>
#include <sstream>
#include <iomanip>
#include <iostream>

// ===== k0lite (verbatim from k0_snn_node.cpp) =====
namespace k0lite {
constexpr uint8_t AX_OK           = 0x00;
constexpr uint8_t AX_SATURATED    = 0x01;
constexpr uint8_t AX_TRUNCATED    = 0x02;
constexpr uint8_t AX_BURST_CROP   = 0x04;
constexpr uint8_t AX_INPUT_RANGE  = 0x08;
constexpr uint8_t AX_DIV_ZERO     = 0x10;

inline int32_t add_sat(int32_t a, int32_t b, uint8_t& st) noexcept {
    int64_t s = static_cast<int64_t>(a) + static_cast<int64_t>(b);
    if (s > INT32_MAX) { st |= AX_SATURATED; return INT32_MAX; }
    if (s < INT32_MIN) { st |= AX_SATURATED; return INT32_MIN; }
    return static_cast<int32_t>(s);
}
inline int32_t mul_normative(int32_t a, int32_t b, uint8_t& st) noexcept {
    int64_t prod = static_cast<int64_t>(a) * static_cast<int64_t>(b);
    uint32_t low16 = static_cast<uint32_t>(prod < 0 ? -prod : prod) & 0xFFFF;
    int64_t q = prod >> 16;
    bool g = (low16 >> 15) & 1;
    bool r = (low16 >> 14) & 1;
    bool s_bit = (low16 & 0x1FFF) != 0;
    bool round_up = g && (r || s_bit || ((q & 1) != 0));
    if (round_up) q += (prod >= 0) ? 1 : -1;
    if (low16 != 0) st |= AX_TRUNCATED;
    if (q > INT32_MAX) { st |= AX_SATURATED; return INT32_MAX; }
    if (q < INT32_MIN) { st |= AX_SATURATED; return INT32_MIN; }
    return static_cast<int32_t>(q);
}
inline int32_t mac(int32_t acc, int32_t a, int32_t b, uint8_t& st) noexcept {
    int32_t p = mul_normative(a, b, st);
    return add_sat(acc, p, st);
}
inline int32_t emit_o1(int32_t v_abs, int32_t theta, int32_t& emit_count,
                       int32_t emit_cap, uint8_t& st) noexcept {
    if (v_abs >= theta) {
        if (emit_count >= emit_cap) { st |= AX_BURST_CROP; return 0; }
        emit_count += 1;
        return 1;
    }
    return 0;
}
inline uint64_t splitmix64(uint64_t& state) noexcept {
    state += 0x9e3779b97f4a7c15ULL;
    uint64_t z = state;
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
    return z ^ (z >> 31);
}
}  // namespace k0lite

// ===== sha256 (verbatim) =====
namespace sha256 {
static const uint32_t K[64] = {
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
};
inline uint32_t rotr(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }
std::array<uint8_t,32> hash(const uint8_t* data, size_t len) {
    uint32_t h[8] = {0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
                     0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    std::vector<uint8_t> msg(data, data + len);
    msg.push_back(0x80);
    while (msg.size() % 64 != 56) msg.push_back(0x00);
    uint64_t bit_len = static_cast<uint64_t>(len) * 8;
    for (int i = 7; i >= 0; i--) msg.push_back((bit_len >> (i * 8)) & 0xFF);
    for (size_t off = 0; off < msg.size(); off += 64) {
        uint32_t w[64];
        for (int i = 0; i < 16; i++) {
            w[i] = (uint32_t(msg[off+i*4])<<24) | (uint32_t(msg[off+i*4+1])<<16) |
                   (uint32_t(msg[off+i*4+2])<<8) | uint32_t(msg[off+i*4+3]);
        }
        for (int i = 16; i < 64; i++) {
            uint32_t s0 = rotr(w[i-15],7)^rotr(w[i-15],18)^(w[i-15]>>3);
            uint32_t s1 = rotr(w[i-2],17)^rotr(w[i-2],19)^(w[i-2]>>10);
            w[i] = w[i-16]+s0+w[i-7]+s1;
        }
        uint32_t a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],hh=h[7];
        for (int i = 0; i < 64; i++) {
            uint32_t S1=rotr(e,6)^rotr(e,11)^rotr(e,25);
            uint32_t ch=(e&f)^(~e&g);
            uint32_t tmp1=hh+S1+ch+K[i]+w[i];
            uint32_t S0=rotr(a,2)^rotr(a,13)^rotr(a,22);
            uint32_t maj=(a&b)^(a&c)^(b&c);
            uint32_t tmp2=S0+maj;
            hh=g; g=f; f=e; e=d+tmp1; d=c; c=b; b=a; a=tmp1+tmp2;
        }
        h[0]+=a; h[1]+=b; h[2]+=c; h[3]+=d;
        h[4]+=e; h[5]+=f; h[6]+=g; h[7]+=hh;
    }
    std::array<uint8_t,32> out;
    for (int i = 0; i < 8; i++) {
        out[i*4+0]=(h[i]>>24)&0xFF; out[i*4+1]=(h[i]>>16)&0xFF;
        out[i*4+2]=(h[i]>>8)&0xFF;  out[i*4+3]=h[i]&0xFF;
    }
    return out;
}
std::string hex(const std::array<uint8_t,32>& b) {
    std::ostringstream ss;
    for (auto x : b) ss << std::hex << std::setw(2) << std::setfill('0') << (int)x;
    return ss.str();
}
}  // namespace sha256

// ===== k0_determinism_run (verbatim from node) =====
std::string k0_determinism_run(int N = 1000) {
    constexpr uint64_t SEED     = 0x123456789abce900ULL;
    constexpr int      EMIT_CAP = 15;
    constexpr int32_t  THETA    = 1 << 15;

    uint64_t state = SEED;
    int32_t  acc   = 0;
    int32_t  emit_count = 0;
    uint8_t  st    = 0;

    std::vector<uint8_t> transcript;
    transcript.reserve(N * 14);
    auto write_le32 = [&](int32_t v) {
        uint32_t u = static_cast<uint32_t>(v);
        transcript.push_back(u & 0xFF); transcript.push_back((u >> 8) & 0xFF);
        transcript.push_back((u >> 16) & 0xFF); transcript.push_back((u >> 24) & 0xFF);
    };
    auto write_le16 = [&](uint16_t v) {
        transcript.push_back(v & 0xFF); transcript.push_back((v >> 8) & 0xFF);
    };
    for (int i = 0; i < N; i++) {
        uint64_t raw = k0lite::splitmix64(state);
        int32_t a = static_cast<int32_t>(raw & 0x00FFFFFF) - 0x007FFFFF;
        raw = k0lite::splitmix64(state);
        int32_t b = static_cast<int32_t>(raw & 0x00FFFFFF) - 0x007FFFFF;
        st = k0lite::AX_OK;
        int32_t mac_val = k0lite::mac(0, a, b, st);
        acc = k0lite::add_sat(acc, mac_val, st);
        int32_t acc_abs = static_cast<int32_t>(
            acc < 0 ? -(static_cast<uint32_t>(acc)) : static_cast<uint32_t>(acc));
        int32_t emit = k0lite::emit_o1(acc_abs, THETA, emit_count, EMIT_CAP, st);
        write_le32(a); write_le32(b);
        write_le16(static_cast<uint16_t>(st)); write_le32(emit);
    }
    auto digest = sha256::hash(transcript.data(), transcript.size());
    return sha256::hex(digest);
}

int main() {
    const int N = 1000;
    std::string h1 = k0_determinism_run(N);
    std::string h2 = k0_determinism_run(N);
    bool ok = (h1 == h2);
    std::cout << "AX_K0_LITE_ROS2_DETERMINISM_TEST N=" << N
              << " run1=" << h1 << " run2=" << h2
              << " PASS=" << (ok ? "true" : "false") << "\n";
    // JSON artifact line (captured by the harness into ros2/results/)
    std::cout << "{\"test\":\"k0_ros2_determinism_standalone\",\"N\":" << N
              << ",\"run1\":\"" << h1 << "\",\"run2\":\"" << h2
              << "\",\"double_run_equal\":" << (ok ? "true" : "false")
              << ",\"source\":\"ros2/k0_snn_controller/src/k0_snn_node.cpp::k0_determinism_run\"}\n";
    return ok ? 0 : 1;
}
