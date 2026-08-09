#ifndef AX_H
#define AX_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// AX raw representation: int64 two's complement, Q32.32
typedef int64_t ax_scalar_t;

enum ax_status_flag {
    AX_SATURATED   = 1u << 0,
    AX_TRUNCATED   = 1u << 1,
    AX_BURST_CROP  = 1u << 2,
    AX_INPUT_RANGE = 1u << 3,
    AX_DIV_ZERO    = 1u << 4,
};

typedef uint32_t ax_status_t;

static inline void ax_status_or(ax_status_t *st, ax_status_t add) {
    if (!st) return;
    *st |= add;
}

ax_scalar_t ax_add_sat(ax_scalar_t a, ax_scalar_t b, ax_status_t *st);
ax_scalar_t ax_mul_normative(ax_scalar_t a, ax_scalar_t b, ax_status_t *st);
ax_scalar_t ax_mac(ax_scalar_t a, ax_scalar_t b, ax_scalar_t acc, ax_status_t *st);

// emit_o1: x>=0, theta>0, emit_cap>=0.
// returns x_new (raw Q32.32). emit_out is non-negative integer.
ax_scalar_t ax_emit_o1(ax_scalar_t x, ax_scalar_t theta, uint64_t emit_cap,
                       uint64_t *emit_out, ax_status_t *st);

#ifdef __cplusplus
}
#endif

#endif
