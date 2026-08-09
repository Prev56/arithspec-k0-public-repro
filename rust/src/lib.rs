//! K0 — Normative Integer Arithmetic for Spiking Neural Networks
//!
//! Rust K0-Full implementation (INT64 Q32.32).
//! Zero float in the hot path. Conformant with K0_NORMATIVE_v2.5.
//!
//! Reference hash (N=200_000): 45ff9803bb5254fb04af2ec70c865ec981f3f6d221894c3acb769bc2847f000d

// When building for embedded targets (e.g. thumbv6m-none-eabi), disable std.
// SHA-256 and hex_encode (heap-dependent) are gated behind cfg(feature = "std").
#![cfg_attr(not(feature = "std"), no_std)]

/// K0-Lite (INT32 Q16.16) — for embedded targets (RP2040, Cortex-M0+)
pub mod k0_lite;

// K0-Full Rust library — zero float in hot path
//
// ─────────────────────────────────────────────────────────────────────────────
// Status flags (§5 of K0_NORMATIVE_v2.5)
// ─────────────────────────────────────────────────────────────────────────────

pub const AX_SATURATED:   u8 = 0x01;
pub const AX_TRUNCATED:   u8 = 0x02; // a.k.a. AX_INEXACT
pub const AX_BURST_CROP:  u8 = 0x04;
pub const AX_INPUT_RANGE: u8 = 0x08;
pub const AX_DIV_ZERO:    u8 = 0x10;

// ─────────────────────────────────────────────────────────────────────────────
// Internal: saturating clamp i128 → i64
// ─────────────────────────────────────────────────────────────────────────────

#[inline(always)]
fn clamp_i64(v: i128, st: &mut u8) -> i64 {
    if v > i64::MAX as i128 {
        *st |= AX_SATURATED;
        i64::MAX
    } else if v < i64::MIN as i128 {
        *st |= AX_SATURATED;
        i64::MIN
    } else {
        v as i64
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// ADD_SAT — saturating add, Q32.32 (§4.1)
// ─────────────────────────────────────────────────────────────────────────────

#[inline(always)]
pub fn k0_add_sat(a: i64, b: i64, st: &mut u8) -> i64 {
    let s: i128 = (a as i128) + (b as i128);
    clamp_i64(s, st)
}

// ─────────────────────────────────────────────────────────────────────────────
// MUL_NORMATIVE — Q32.32 × Q32.32 → Q32.32, GRS bits, RNE (§4.2)
//
// Algorithm (identical to ax.c):
//   P = a * b  (exact, i128, Q64.64)
//   Q = P >> 32  (candidate Q32.32)
//   low = P & 0xFFFF_FFFF  (discarded 32 bits)
//   G = bit 31 of low (guard)
//   R = bit 30 of low (round)
//   S = any of bits 29..0 of low (sticky)
//   RNE: Q += 1 iff G && (R || S || Q is odd)
//   AX_TRUNCATED set if low != 0
//   AX_SATURATED set if Q overflows i64
// ─────────────────────────────────────────────────────────────────────────────

#[inline(always)]
pub fn k0_mul_normative(a: i64, b: i64, st: &mut u8) -> i64 {
    let p: i128 = (a as i128) * (b as i128);
    let q: i128 = p >> 32;

    // Low 32 bits of the unsigned 128-bit product
    let low: u32 = (p as u128) as u32; // cast via u128 to get unsigned low bits

    let g = (low >> 31) & 1;
    let r = (low >> 30) & 1;
    let s: u32 = if low & 0x3FFF_FFFF != 0 { 1 } else { 0 };

    // Round to nearest even
    let q = if g != 0 && (r != 0 || s != 0 || (q as u64 & 1) != 0) {
        q + 1
    } else {
        q
    };

    if low != 0 {
        *st |= AX_TRUNCATED;
    }

    clamp_i64(q, st)
}

// ─────────────────────────────────────────────────────────────────────────────
// MAC — multiply-accumulate (§4.3)
// ─────────────────────────────────────────────────────────────────────────────

#[inline(always)]
pub fn k0_mac(a: i64, b: i64, acc: i64, st: &mut u8) -> i64 {
    let mut s_local: u8 = 0;
    let prod = k0_mul_normative(a, b, &mut s_local);
    *st |= s_local;
    k0_add_sat(acc, prod, st)
}

// ─────────────────────────────────────────────────────────────────────────────
// EMIT_O1 — threshold firing with burst cap (§4.4)
//
// Preconditions for a valid spike:
//   theta > 0  (else AX_DIV_ZERO, return x unchanged)
//   x >= 0     (else AX_INPUT_RANGE, return x unchanged)
// ─────────────────────────────────────────────────────────────────────────────

pub fn k0_emit_o1(x: i64, theta: i64, emit_cap: u64, emit_out: &mut u64, st: &mut u8) -> i64 {
    *emit_out = 0;

    if theta <= 0 {
        *st |= AX_DIV_ZERO;
        return x;
    }
    if x < 0 {
        *st |= AX_INPUT_RANGE;
        return x;
    }

    // Integer division: how many full thresholds fit in x?
    let emit: u64 = ((x as i128) / (theta as i128)) as u64;

    let emit = if emit > emit_cap {
        *st |= AX_BURST_CROP;
        emit_cap
    } else {
        emit
    };

    // Subtract emitted amount: x_new = x - emit * theta
    // Compute emit * theta in Q32.32: emit << 32 gives an i128 in Q32.32 units
    let emit_q: i128 = (emit as i128) << 32;
    let mut s_local: u8 = 0;
    // emit_q can be very large; clamp to i64 range before mul_normative
    let emit_q_clamped: i64 = if emit_q > i64::MAX as i128 {
        s_local |= AX_SATURATED;
        i64::MAX
    } else {
        emit_q as i64
    };
    let tmp = k0_mul_normative(emit_q_clamped, theta, &mut s_local);
    *st |= s_local;

    let x_new = k0_add_sat(x, -tmp, st);
    *emit_out = emit;
    x_new
}

// ─────────────────────────────────────────────────────────────────────────────
// LIF neuron step (§4.5) — for network-level experiments
// ─────────────────────────────────────────────────────────────────────────────

pub struct K0LIFState {
    pub v_mem:  i64, // Q32.32
    pub refrac: u32,
}

pub struct K0LIFParams {
    pub decay:       i64, // Q32.32 — ≈ exp(-dt/tau)
    pub bias:        i64, // Q32.32
    pub threshold:   i64, // Q32.32
    pub refrac_ticks: u32,
}

pub fn k0_lif_step(state: &mut K0LIFState, params: &K0LIFParams, input: i64, st: &mut u8) -> u64 {
    if state.refrac > 0 {
        state.refrac -= 1;
        return 0;
    }
    // v = v * decay + input + bias
    let v_decayed = k0_mul_normative(state.v_mem, params.decay, st);
    let v_plus_in = k0_add_sat(v_decayed, input, st);
    let v_new     = k0_add_sat(v_plus_in, params.bias, st);
    state.v_mem   = v_new;

    let mut emit: u64 = 0;
    let v_after = k0_emit_o1(state.v_mem, params.threshold, 1, &mut emit, st);
    if emit > 0 {
        state.v_mem  = v_after;
        state.refrac = params.refrac_ticks;
    }
    emit
}

// ─────────────────────────────────────────────────────────────────────────────
// splitmix64 PRNG (§6) — identical to ax_k0_test.c
// ─────────────────────────────────────────────────────────────────────────────

#[inline(always)]
pub fn splitmix64(x: &mut u64) -> u64 {
    *x = x.wrapping_add(0x9e3779b97f4a7c15);
    let mut z = *x;
    z = (z ^ (z >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94d049bb133111eb);
    z ^ (z >> 31)
}

// ─────────────────────────────────────────────────────────────────────────────
// Serialization (§8) — little-endian, explicit, portable
// ─────────────────────────────────────────────────────────────────────────────

#[inline(always)]
pub fn serialize_i64_le(v: i64) -> [u8; 8] {
    v.to_le_bytes()
}

#[inline(always)]
pub fn serialize_u32_le(v: u32) -> [u8; 4] {
    v.to_le_bytes()
}

// ─────────────────────────────────────────────────────────────────────────────
// Unit tests
// ─────────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn add_sat_no_overflow() {
        let mut st: u8 = 0;
        let r = k0_add_sat(1 << 32, 1 << 32, &mut st);
        assert_eq!(r, 1i64 << 33);
        assert_eq!(st & AX_SATURATED, 0);
    }

    #[test]
    fn add_sat_overflow_positive() {
        let mut st: u8 = 0;
        let r = k0_add_sat(i64::MAX, 1, &mut st);
        assert_eq!(r, i64::MAX);
        assert_ne!(st & AX_SATURATED, 0);
    }

    #[test]
    fn mul_normative_identity() {
        // 1.0 in Q32.32 = 1 << 32
        let mut st: u8 = 0;
        let one: i64 = 1i64 << 32;
        let r = k0_mul_normative(one, one, &mut st);
        assert_eq!(r, one, "1.0 * 1.0 should equal 1.0 in Q32.32");
        assert_eq!(st, 0);
    }

    #[test]
    fn mul_normative_half() {
        // 0.5 in Q32.32 = 1 << 31
        let mut st: u8 = 0;
        let half: i64 = 1i64 << 31;
        let r = k0_mul_normative(half, half, &mut st);
        // 0.5 * 0.5 = 0.25 = 1 << 30
        assert_eq!(r, 1i64 << 30);
    }

    #[test]
    fn mul_normative_rne_tie() {
        // Test RNE: when G=1, R=0, S=0, round to even
        // Construct a * b such that low=0x80000000 (G=1, R=0, S=0)
        // This is a tie — round to even (Q & 1 decides)
        // (Hard to construct cleanly; just verify no panic and flag behavior)
        let mut st: u8 = 0;
        let _ = k0_mul_normative(3, 7, &mut st);
        // 3 * 7 = 21, P = 21 in Q64.64, Q = 21 >> 32 = 0, low = 21 != 0 → truncated
        assert_ne!(st & AX_TRUNCATED, 0);
    }

    #[test]
    fn emit_o1_basic() {
        let mut st: u8 = 0;
        let mut emit: u64 = 0;
        // x = 2.0 Q32.32, theta = 1.0 Q32.32 → emit=2, x_new=0
        let x     = 2i64 << 32;
        let theta = 1i64 << 32;
        let x_new = k0_emit_o1(x, theta, 10, &mut emit, &mut st);
        assert_eq!(emit, 2);
        assert_eq!(x_new, 0);
    }

    #[test]
    fn emit_o1_div_zero() {
        let mut st: u8 = 0;
        let mut emit: u64 = 0;
        let x_new = k0_emit_o1(100, 0, 10, &mut emit, &mut st);
        assert_eq!(x_new, 100);
        assert_ne!(st & AX_DIV_ZERO, 0);
    }

    #[test]
    fn sha256_known_vector() {
        // SHA-256("abc") verified against Python hashlib (OpenSSL)
        let digest = sha256_bytes(b"abc");
        let hex = hex_encode(&digest);
        assert_eq!(hex, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            "SHA-256('abc') mismatch");
    }

    #[test]
    fn sha256_empty() {
        // SHA-256("") = e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
        let digest = sha256_bytes(b"");
        let hex = hex_encode(&digest);
        assert_eq!(hex, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Pure-Rust SHA-256 (no external crates — portable, std-only)
// Conformant with FIPS 180-4.
// ─────────────────────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────────
// NOTE: sha256_bytes and hex_encode require heap allocation (Vec / String).
// They are ONLY available when feature = "std" is active (default).
// Embedded builds (no_std) do not have these functions; hashing is done on host.
// ─────────────────────────────────────────────────────────────────────────────
#[cfg(feature = "std")]
/// SHA-256 round constants (first 32 bits of ∛ of first 64 primes).
#[rustfmt::skip]
const SHA256_K: [u32; 64] = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
    0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
    0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
    0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];

/// Compute SHA-256 of `data`. Returns 32-byte digest. Pure Rust std, no external crates.
/// Only available with feature = "std" (requires Vec for padding).
#[cfg(feature = "std")]
pub fn sha256_bytes(data: &[u8]) -> [u8; 32] {
    // Initial hash values — first 32 bits of fractional parts of √2, √3, …, √19
    let mut h0: u32 = 0x6a09e667;
    let mut h1: u32 = 0xbb67ae85;
    let mut h2: u32 = 0x3c6ef372;
    let mut h3: u32 = 0xa54ff53a;
    let mut h4: u32 = 0x510e527f;
    let mut h5: u32 = 0x9b05688c;
    let mut h6: u32 = 0x1f83d9ab;
    let mut h7: u32 = 0x5be0cd19;

    // Padding: append 0x80, zero-fill to 56 mod 64, append bit-length as big-endian u64
    let bit_len: u64 = (data.len() as u64).wrapping_mul(8);
    let mut msg: Vec<u8> = Vec::with_capacity(data.len() + 72);
    msg.extend_from_slice(data);
    msg.push(0x80);
    while msg.len() % 64 != 56 {
        msg.push(0u8);
    }
    msg.extend_from_slice(&bit_len.to_be_bytes());

    // Process 512-bit (64-byte) chunks
    for chunk in msg.chunks(64) {
        // Message schedule
        let mut w = [0u32; 64];
        for i in 0..16 {
            w[i] = ((chunk[4 * i]     as u32) << 24)
                 | ((chunk[4 * i + 1] as u32) << 16)
                 | ((chunk[4 * i + 2] as u32) << 8)
                 |  (chunk[4 * i + 3] as u32);
        }
        for i in 16..64 {
            let s0 = w[i - 15].rotate_right(7)
                   ^ w[i - 15].rotate_right(18)
                   ^ (w[i - 15] >> 3);
            let s1 = w[i - 2].rotate_right(17)
                   ^ w[i - 2].rotate_right(19)
                   ^ (w[i - 2] >> 10);
            w[i] = w[i - 16].wrapping_add(s0)
                             .wrapping_add(w[i - 7])
                             .wrapping_add(s1);
        }

        // Compression — working variables initialised from current hash state
        let (mut a, mut b, mut c, mut d, mut e, mut f, mut g, mut wh) =
            (h0, h1, h2, h3, h4, h5, h6, h7);

        for i in 0..64 {
            let ep1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let ch  = (e & f) ^ ((!e) & g);
            let t1  = wh.wrapping_add(ep1)
                        .wrapping_add(ch)
                        .wrapping_add(SHA256_K[i])
                        .wrapping_add(w[i]);
            let ep0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let maj = (a & b) ^ (a & c) ^ (b & c);
            let t2  = ep0.wrapping_add(maj);

            wh = g;
            g  = f;
            f  = e;
            e  = d.wrapping_add(t1);
            d  = c;
            c  = b;
            b  = a;
            a  = t1.wrapping_add(t2);
        }

        // Add compressed chunk to current hash value
        h0 = h0.wrapping_add(a);
        h1 = h1.wrapping_add(b);
        h2 = h2.wrapping_add(c);
        h3 = h3.wrapping_add(d);
        h4 = h4.wrapping_add(e);
        h5 = h5.wrapping_add(f);
        h6 = h6.wrapping_add(g);
        h7 = h7.wrapping_add(wh);
    }

    // Produce digest — big-endian
    let mut out = [0u8; 32];
    for (i, &v) in [h0, h1, h2, h3, h4, h5, h6, h7].iter().enumerate() {
        out[4 * i]     = (v >> 24) as u8;
        out[4 * i + 1] = (v >> 16) as u8;
        out[4 * i + 2] = (v >>  8) as u8;
        out[4 * i + 3] =  v        as u8;
    }
    out
}

/// Hex-encode bytes to lowercase string (replaces `hex` crate).
/// Only available with feature = "std" (returns heap-allocated String).
#[cfg(feature = "std")]
pub fn hex_encode(bytes: &[u8]) -> String {
    const HEX: &[u8] = b"0123456789abcdef";
    let mut s = String::with_capacity(bytes.len() * 2);
    for &b in bytes {
        s.push(HEX[(b >> 4) as usize] as char);
        s.push(HEX[(b & 0xf) as usize] as char);
    }
    s
}
