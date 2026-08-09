//! K0 conformance test — Rust port
//!
//! Produces SHA-256 over 200_000 canonical iterations.
//! Expected: 45ff9803bb5254fb04af2ec70c865ec981f3f6d221894c3acb769bc2847f000d

use k0::{k0_add_sat, k0_mul_normative, k0_emit_o1, splitmix64, serialize_i64_le, serialize_u32_le, sha256_bytes, hex_encode};

const N: usize = 200_000;
// seed = 0xA10 + 0x123456789abcdef0 = 0x123456789abce900
const SEED: u64 = 0x123456789abce900u64;

fn run_k0_test(n: usize) -> String {
    let mut seed = SEED;
    // Collect transcript into a flat byte buffer, then SHA-256 once
    let mut buf: Vec<u8> = Vec::with_capacity(n * (8 * 4 + 4));

    for _ in 0..n {
        let mut st: u8 = 0;

        // Inputs — identical mapping to ax_k0_test.c as_scalar() = raw i64 cast
        let a     = splitmix64(&mut seed) as i64;
        let b     = splitmix64(&mut seed) as i64;
        let x     = splitmix64(&mut seed) as i64;
        let theta = (splitmix64(&mut seed) | 1) as i64; // avoid 0
        let cap   = (splitmix64(&mut seed) % 128) + 1;  // 1..128

        // Ops
        let r_add = k0_add_sat(a, b, &mut st);
        let r_mul = k0_mul_normative(a, b, &mut st);

        let mut emit: u64 = 0;
        let x2 = k0_emit_o1(x, theta, cap, &mut emit, &mut st);

        // Canonical transcript: feed_u64 × 4 + feed_u32 × 1 (little-endian)
        buf.extend_from_slice(&serialize_i64_le(r_add));
        buf.extend_from_slice(&serialize_i64_le(r_mul));
        buf.extend_from_slice(&serialize_i64_le(x2));
        buf.extend_from_slice(&serialize_i64_le(emit as i64));
        buf.extend_from_slice(&serialize_u32_le(st as u32));
    }

    hex_encode(&sha256_bytes(&buf))
}

fn main() {
    let hash = run_k0_test(N);
    println!("AX_K0_TEST_SHA256={}", hash);
}

#[cfg(test)]
mod conformance {
    use super::*;

    const REF_HASH: &str = "45ff9803bb5254fb04af2ec70c865ec981f3f6d221894c3acb769bc2847f000d";

    #[test]
    fn k0_conformance_sha256() {
        let hash = run_k0_test(N);
        assert_eq!(
            hash, REF_HASH,
            "\nK0 conformance FAIL\n  got : {}\n  want: {}", hash, REF_HASH
        );
    }
}
