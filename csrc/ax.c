#include "ax.h"
#include <limits.h>

#define INT64_MIN_V ((int64_t)INT64_MIN)
#define INT64_MAX_V ((int64_t)INT64_MAX)

static inline ax_scalar_t clamp_int64(__int128 v, ax_status_t *st) {
    if (v > (__int128)INT64_MAX_V) {
        ax_status_or(st, AX_SATURATED);
        return INT64_MAX_V;
    }
    if (v < (__int128)INT64_MIN_V) {
        ax_status_or(st, AX_SATURATED);
        return INT64_MIN_V;
    }
    return (ax_scalar_t)v;
}

ax_scalar_t ax_add_sat(ax_scalar_t a, ax_scalar_t b, ax_status_t *st) {
    __int128 s = (__int128)a + (__int128)b;
    return clamp_int64(s, st);
}

// Q32.32 * Q32.32 -> Q64.64 exact (int128), then RNE (ties-to-even) to Q32.32,
// saturation after rounding.
ax_scalar_t ax_mul_normative(ax_scalar_t a, ax_scalar_t b, ax_status_t *st) {
    __int128 P = (__int128)a * (__int128)b;  // Q64.64 exact
    __int128 Q = (P >> 32);                  // candidate Q32.32

    uint32_t low = (uint32_t)(((__uint128_t)P) & 0xFFFFFFFFu);

    uint32_t g = (low >> 31) & 1u;
    uint32_t r = (low >> 30) & 1u;
    uint32_t s = (low & 0x3FFFFFFFu) ? 1u : 0u;

    if (g && (r || s || ((uint32_t)Q & 1u))) {
        Q += 1;
    }

    if (low != 0u) {
        ax_status_or(st, AX_TRUNCATED);
    }

    return clamp_int64(Q, st);
}

ax_scalar_t ax_mac(ax_scalar_t a, ax_scalar_t b, ax_scalar_t acc, ax_status_t *st) {
    ax_status_t s_local = 0;
    ax_scalar_t prod = ax_mul_normative(a, b, &s_local);
    ax_status_or(st, s_local);
    return ax_add_sat(acc, prod, st);
}

ax_scalar_t ax_emit_o1(ax_scalar_t x, ax_scalar_t theta, uint64_t emit_cap,
                       uint64_t *emit_out, ax_status_t *st) {
    if (emit_out) *emit_out = 0;

    if (theta <= 0) {
        ax_status_or(st, AX_DIV_ZERO);
        return x;
    }
    if (x < 0) {
        ax_status_or(st, AX_INPUT_RANGE);
        return x;
    }

    uint64_t emit = (uint64_t)((__int128)x / (__int128)theta);

    if (emit > emit_cap) {
        emit = emit_cap;
        ax_status_or(st, AX_BURST_CROP);
    }

    __int128 emit_q = ((__int128)emit) << 32;
    ax_status_t s_local = 0;
    ax_scalar_t tmp = ax_mul_normative((ax_scalar_t)emit_q, theta, &s_local);
    ax_status_or(st, s_local);

    ax_scalar_t x_new = ax_add_sat(x, (ax_scalar_t)(-tmp), st);

    if (emit_out) *emit_out = emit;
    return x_new;
}
