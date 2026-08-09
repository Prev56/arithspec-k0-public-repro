// K0-Lite — INT32 Q16.16 normative arithmetic
//
// Mirror of K0-Full (INT64 Q32.32) at half precision.
// Designed for no_std / embedded targets (RP2040, Cortex-M0+).
//
// Spec: K0_NORMATIVE_v2.5.md §K0-Lite
// Every operation mirrors ax_lite_mul_normative / ax_lite_add_sat in C.
//
// no_std is controlled at the crate root (lib.rs) via cfg_attr.
// This module is fully no_std-compatible: no heap, no std, stack-only.

// ─────────────────────────────────────────────────────────────────────────────
// Status flags — identical bit positions to K0-Full
// ─────────────────────────────────────────────────────────────────────────────
pub const AX_OK:           u8 = 0x00;
pub const AX_SATURATED:    u8 = 0x01;
pub const AX_TRUNCATED:    u8 = 0x02;
pub const AX_BURST_CROP:   u8 = 0x04;
pub const AX_INPUT_RANGE:  u8 = 0x08;
pub const AX_DIV_ZERO:     u8 = 0x10;

// ─────────────────────────────────────────────────────────────────────────────
// Internal: saturating clamp i64 → i32
// ─────────────────────────────────────────────────────────────────────────────
#[inline(always)]
fn clamp_i32(v: i64, st: &mut u8) -> i32 {
    if v > i32::MAX as i64 {
        *st |= AX_SATURATED;
        i32::MAX
    } else if v < i32::MIN as i64 {
        *st |= AX_SATURATED;
        i32::MIN
    } else {
        v as i32
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// ADD_SAT — saturating add, Q16.16 (§K0-Lite §4.1)
// ─────────────────────────────────────────────────────────────────────────────
#[inline(always)]
pub fn k0_lite_add_sat(a: i32, b: i32, st: &mut u8) -> i32 {
    let s: i64 = (a as i64) + (b as i64);
    clamp_i32(s, st)
}

// ─────────────────────────────────────────────────────────────────────────────
// MUL_NORMATIVE — Q16.16 × Q16.16 → Q16.16, GRS bits, RNE (§K0-Lite §4.2)
//
// Algorithm (mirrors ax_lite_mul_normative in C):
//   P = a * b  (exact, i64, Q32.32)
//   Q = P >> 16  (candidate Q16.16)
//   low16 = (P as u32) & 0xFFFF  (discarded 16 fractional bits)
//   low_u32 = (P as u32)         (unsigned low 32 bits)
//   G = bit 15 of low_u32 (guard)
//   R = bit 14 of low_u32 (round)
//   S = any of bits 13..0 of low_u32 (sticky)
//   RNE: Q += 1 iff G && (R || S || Q is odd)
//   AX_TRUNCATED set if low 16 bits != 0
//   AX_SATURATED set if Q overflows i32
// ─────────────────────────────────────────────────────────────────────────────
#[inline(always)]
pub fn k0_lite_mul_normative(a: i32, b: i32, st: &mut u8) -> i32 {
    let p: i64 = (a as i64) * (b as i64);
    let q: i64 = p >> 16;

    // Low 32 bits of product (via u64 cast to get unsigned representation)
    let low_u32: u32 = (p as u64) as u32;
    // The 16 fractional bits we discard
    let low16: u32 = low_u32 & 0x0000_FFFF;

    // GRS from positions 15, 14, 13..0 of low_u32
    let g: u32 = (low_u32 >> 15) & 1;
    let r: u32 = (low_u32 >> 14) & 1;
    let s: u32 = if low_u32 & 0x0000_3FFF != 0 { 1 } else { 0 };

    // AX_TRUNCATED if any fractional bit was lost
    if low16 != 0 {
        *st |= AX_TRUNCATED;
    }

    // Round to nearest even
    let q_rounded: i64 = if g != 0 && (r != 0 || s != 0 || (q & 1) != 0) {
        q + 1
    } else {
        q
    };

    clamp_i32(q_rounded, st)
}

// ─────────────────────────────────────────────────────────────────────────────
// MAC — multiply-accumulate
// ─────────────────────────────────────────────────────────────────────────────
#[inline(always)]
pub fn k0_lite_mac(a: i32, b: i32, acc: i32, st: &mut u8) -> i32 {
    let mut s_local: u8 = 0;
    let prod = k0_lite_mul_normative(a, b, &mut s_local);
    *st |= s_local;
    k0_lite_add_sat(acc, prod, st)
}

// ─────────────────────────────────────────────────────────────────────────────
// EMIT_O1 — threshold firing with burst cap (K0-Lite §4.4)
// ─────────────────────────────────────────────────────────────────────────────
pub fn k0_lite_emit_o1(
    x: i32,
    theta: i32,
    emit_cap: u32,
    emit_out: &mut u32,
    st: &mut u8,
) -> i32 {
    *emit_out = 0;
    if theta <= 0 {
        *st |= AX_DIV_ZERO;
        return x;
    }
    if x < 0 {
        *st |= AX_INPUT_RANGE;
        return x;
    }
    let emit: u32 = ((x as i64) / (theta as i64)) as u32;
    let emit = if emit > emit_cap {
        *st |= AX_BURST_CROP;
        emit_cap
    } else {
        emit
    };
    let sub: i64 = (emit as i64) * (theta as i64);
    let x_new = k0_lite_add_sat(x, -(sub as i32), st);
    *emit_out = emit;
    x_new
}

// ─────────────────────────────────────────────────────────────────────────────
// splitmix64 PRNG — identical to K0-Full (determinism across variants)
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
// Serialization — little-endian i32/u16 for transcript
// ─────────────────────────────────────────────────────────────────────────────
#[inline(always)]
pub fn serialize_i32_le(v: i32) -> [u8; 4] {
    v.to_le_bytes()
}

#[inline(always)]
pub fn serialize_u16_le(v: u16) -> [u8; 2] {
    v.to_le_bytes()
}

// ─────────────────────────────────────────────────────────────────────────────
// Unit tests (std only)
// ─────────────────────────────────────────────────────────────────────────────
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lite_add_sat_no_overflow() {
        let mut st: u8 = 0;
        let r = k0_lite_add_sat(1 << 16, 1 << 16, &mut st);
        assert_eq!(r, 1i32 << 17);
        assert_eq!(st & AX_SATURATED, 0);
    }

    #[test]
    fn lite_add_sat_overflow_positive() {
        let mut st: u8 = 0;
        let r = k0_lite_add_sat(i32::MAX, 1, &mut st);
        assert_eq!(r, i32::MAX);
        assert_ne!(st & AX_SATURATED, 0);
    }

    #[test]
    fn lite_mul_identity() {
        // 1.0 in Q16.16 = 1 << 16
        let mut st: u8 = 0;
        let one: i32 = 1i32 << 16;
        let r = k0_lite_mul_normative(one, one, &mut st);
        assert_eq!(r, one, "1.0 * 1.0 should equal 1.0 in Q16.16");
        assert_eq!(st & AX_SATURATED, 0);
    }

    #[test]
    fn lite_mul_half() {
        // 0.5 in Q16.16 = 1 << 15
        let mut st: u8 = 0;
        let half: i32 = 1i32 << 15;
        let r = k0_lite_mul_normative(half, half, &mut st);
        // 0.5 * 0.5 = 0.25 = 1 << 14
        assert_eq!(r, 1i32 << 14, "0.5 * 0.5 should equal 0.25 in Q16.16");
    }

    #[test]
    fn lite_mul_truncated_flag() {
        let mut st: u8 = 0;
        let _ = k0_lite_mul_normative(3, 7, &mut st);
        assert_ne!(st & AX_TRUNCATED, 0, "non-aligned product should set TRUNCATED");
    }

    #[test]
    fn lite_emit_o1_basic() {
        let mut st: u8 = 0;
        let mut emit: u32 = 0;
        let x     = 2i32 << 16; // 2.0 Q16.16
        let theta = 1i32 << 16; // 1.0 Q16.16
        let x_new = k0_lite_emit_o1(x, theta, 10, &mut emit, &mut st);
        assert_eq!(emit, 2);
        assert_eq!(x_new, 0);
    }

    #[test]
    fn lite_emit_div_zero() {
        let mut st: u8 = 0;
        let mut emit: u32 = 0;
        let x_new = k0_lite_emit_o1(100, 0, 10, &mut emit, &mut st);
        assert_eq!(x_new, 100);
        assert_ne!(st & AX_DIV_ZERO, 0);
    }
}
