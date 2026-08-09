use k0::{splitmix64, sha256_bytes, hex_encode};
use k0::k0_lite::{k0_lite_add_sat, k0_lite_mul_normative, k0_lite_emit_o1, serialize_i32_le, serialize_u16_le};
fn main() {
    const N: usize = 5;
    const SEED: u64 = 0x123456789abce900;
    const EMIT_CAP: u32 = 15;
    const THETA: i32 = 1i32 << 15;
    let mut rng = SEED; let mut acc: i32 = 0;
    for i in 0..N {
        let raw_a = splitmix64(&mut rng); let raw_b = splitmix64(&mut rng);
        let a: i32 = ((raw_a & 0x00FF_FFFF) as i32).wrapping_sub(0x007F_FFFF);
        let b: i32 = ((raw_b & 0x00FF_FFFF) as i32).wrapping_sub(0x007F_FFFF);
        let mut st: u8 = 0;
        let mac = k0_lite_mul_normative(a, b, &mut st);
        let add = k0_lite_add_sat(acc, mac, &mut st);
        acc = add;
        let mut emit: u32 = 0;
        let v_new = k0_lite_emit_o1(add.abs(), THETA, EMIT_CAP, &mut emit, &mut st);
        println!("i={} a={} b={} mac={} add={} st={} emit={} v_new={}", i, a, b, mac, add, st, emit, v_new);
    }
}
