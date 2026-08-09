/// K0-Lite conformance test — N=200_000 iterations
/// Produces AX_K0_LITE_TEST_SHA256=<hash> using splitmix64 seed 0x123456789abce900
///
/// This binary uses std SHA-256 (same pure-Rust implementation as k0_test.rs).
/// The hash produced is the K0-Lite reference hash (distinct from K0-Full 45ff9803...).

use k0::{splitmix64, sha256_bytes, hex_encode};
use k0::k0_lite::{
    k0_lite_add_sat, k0_lite_mul_normative, k0_lite_emit_o1, serialize_i32_le, serialize_u16_le,
};

/// K0-Lite conformance test protocol (§K0-Lite §7):
/// Same splitmix64 PRNG seed as K0-Full.
/// Per iteration: generate a_raw, b_raw (u64→i32 via truncation to 32 bits).
/// a = (raw >> 16) as i32  — Q16.16 with integer part
/// b = (raw & 0xFFFFFFFF) as i32 — Q16.16 input
/// Then: mac = k0_lite_mul_normative(a, b); add = k0_lite_add_sat(acc, mac)
/// Transcript: serialize_i32_le(mac) ++ serialize_i32_le(add) ++ serialize_u16_le(emit as u16) ++ serialize_i32_le(v_new)
fn main() {
    const N: usize = 200_000;
    const SEED: u64 = 0x123456789abce900;
    const EMIT_CAP: u32 = 15;
    const THETA: i32 = 1i32 << 15;  // 0.5 in Q16.16 — LIF threshold

    let mut rng = SEED;
    let mut acc: i32 = 0;
    // Pre-allocate transcript buffer: 4+4+2+4 = 14 bytes per iteration
    let mut buf: Vec<u8> = Vec::with_capacity(N * 14);

    for _ in 0..N {
        let raw_a = splitmix64(&mut rng);
        let raw_b = splitmix64(&mut rng);

        // Scale to Q16.16 range: keep lower 24 bits, sign via cast
        let a: i32 = ((raw_a & 0x00FF_FFFF) as i32).wrapping_sub(0x007F_FFFF);
        let b: i32 = ((raw_b & 0x00FF_FFFF) as i32).wrapping_sub(0x007F_FFFF);

        let mut st: u8 = 0;
        let mac = k0_lite_mul_normative(a, b, &mut st);
        let add = k0_lite_add_sat(acc, mac, &mut st);
        acc = add;

        // Emit
        let mut emit: u32 = 0;
        let v_new = k0_lite_emit_o1(
            add.abs(),   // |acc| as "potential" for LIF firing test
            THETA,
            EMIT_CAP,
            &mut emit,
            &mut st,
        );

        buf.extend_from_slice(&serialize_i32_le(mac));
        buf.extend_from_slice(&serialize_i32_le(add));
        buf.extend_from_slice(&serialize_u16_le(emit as u16));
        buf.extend_from_slice(&serialize_i32_le(v_new));
    }

    let digest = sha256_bytes(&buf);
    let hex = hex_encode(&digest);
    println!("AX_K0_LITE_TEST_SHA256={}", hex);
}

#[cfg(test)]
mod conformance {
    use super::*;
    use k0::{splitmix64, sha256_bytes, hex_encode};
    use k0::k0_lite::{
        k0_lite_add_sat, k0_lite_mul_normative, k0_lite_emit_o1,
        serialize_i32_le, serialize_u16_le,
    };

    /// K0-Lite conformance test — must produce same hash on all platforms.
    /// This hash is established on first run and locked here.
    #[test]
    fn k0_lite_conformance_sha256() {
        const N: usize = 200_000;
        const SEED: u64 = 0x123456789abce900;
        const EMIT_CAP: u32 = 15;
        const THETA: i32 = 1i32 << 15;

        let mut rng = SEED;
        let mut acc: i32 = 0;
        let mut buf: Vec<u8> = Vec::with_capacity(N * 14);

        for _ in 0..N {
            let raw_a = splitmix64(&mut rng);
            let raw_b = splitmix64(&mut rng);
            let a: i32 = ((raw_a & 0x00FF_FFFF) as i32).wrapping_sub(0x007F_FFFF);
            let b: i32 = ((raw_b & 0x00FF_FFFF) as i32).wrapping_sub(0x007F_FFFF);

            let mut st: u8 = 0;
            let mac = k0_lite_mul_normative(a, b, &mut st);
            let add = k0_lite_add_sat(acc, mac, &mut st);
            acc = add;

            let mut emit: u32 = 0;
            let v_new = k0_lite_emit_o1(add.abs(), THETA, EMIT_CAP, &mut emit, &mut st);

            buf.extend_from_slice(&serialize_i32_le(mac));
            buf.extend_from_slice(&serialize_i32_le(add));
            buf.extend_from_slice(&serialize_u16_le(emit as u16));
            buf.extend_from_slice(&serialize_i32_le(v_new));
        }

        let digest = sha256_bytes(&buf);
        let hex = hex_encode(&digest);
        // Hash established on first certified run — DO NOT change without re-certifying
        // aarch64 + x86-64 must produce the same value for K0-Lite-Conformant
        println!("AX_K0_LITE_TEST_SHA256={}", hex);
        // K0-Lite reference hash — certified x86_64-windows 2026-06-08
        // Must match on aarch64 (Pi5) and thumbv6m (RP2040) for full certification
        const K0_LITE_REF: &str =
            "e1606bef1b34afe155adeace4aae7fd2aa22f0236ada22a61dd71631baae050a";
        assert_eq!(hex, K0_LITE_REF,
            "K0-Lite hash mismatch — implementation diverges from certified reference");
    }
}
