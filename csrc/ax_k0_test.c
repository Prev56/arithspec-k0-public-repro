#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "ax.h"

/*
  K0 deterministic test:
  - purely arithmetic, bit-exact
  - independent of timing/OS
  - produces a single SHA-256 over a canonical byte stream
*/

/* ---------------- minimal SHA-256 (public domain style) ---------------- */
typedef struct {
  uint32_t state[8];
  uint64_t bitlen;
  uint8_t  data[64];
  uint32_t datalen;
} sha256_ctx;

static uint32_t rotr32(uint32_t x, uint32_t n){ return (x>>n) | (x<<(32-n)); }
static uint32_t ch(uint32_t x,uint32_t y,uint32_t z){ return (x & y) ^ (~x & z); }
static uint32_t maj(uint32_t x,uint32_t y,uint32_t z){ return (x & y) ^ (x & z) ^ (y & z); }
static uint32_t e0(uint32_t x){ return rotr32(x,2) ^ rotr32(x,13) ^ rotr32(x,22); }
static uint32_t e1(uint32_t x){ return rotr32(x,6) ^ rotr32(x,11) ^ rotr32(x,25); }
static uint32_t s0(uint32_t x){ return rotr32(x,7) ^ rotr32(x,18) ^ (x>>3); }
static uint32_t s1(uint32_t x){ return rotr32(x,17) ^ rotr32(x,19) ^ (x>>10); }

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

static void sha256_transform(sha256_ctx *ctx, const uint8_t data[64]){
  uint32_t m[64];
  for(int i=0;i<16;i++){
    m[i] = ((uint32_t)data[i*4+0]<<24) | ((uint32_t)data[i*4+1]<<16) |
           ((uint32_t)data[i*4+2]<<8)  | ((uint32_t)data[i*4+3]);
  }
  for(int i=16;i<64;i++){
    m[i] = s1(m[i-2]) + m[i-7] + s0(m[i-15]) + m[i-16];
  }

  uint32_t a=ctx->state[0],b=ctx->state[1],c=ctx->state[2],d=ctx->state[3];
  uint32_t e=ctx->state[4],f=ctx->state[5],g=ctx->state[6],h=ctx->state[7];

  for(int i=0;i<64;i++){
    uint32_t t1 = h + e1(e) + ch(e,f,g) + K[i] + m[i];
    uint32_t t2 = e0(a) + maj(a,b,c);
    h=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+t2;
  }

  ctx->state[0]+=a; ctx->state[1]+=b; ctx->state[2]+=c; ctx->state[3]+=d;
  ctx->state[4]+=e; ctx->state[5]+=f; ctx->state[6]+=g; ctx->state[7]+=h;
}

static void sha256_init(sha256_ctx *ctx){
  ctx->datalen=0; ctx->bitlen=0;
  ctx->state[0]=0x6a09e667; ctx->state[1]=0xbb67ae85; ctx->state[2]=0x3c6ef372; ctx->state[3]=0xa54ff53a;
  ctx->state[4]=0x510e527f; ctx->state[5]=0x9b05688c; ctx->state[6]=0x1f83d9ab; ctx->state[7]=0x5be0cd19;
}

static void sha256_update(sha256_ctx *ctx, const uint8_t *data, size_t len){
  for(size_t i=0;i<len;i++){
    ctx->data[ctx->datalen++] = data[i];
    if(ctx->datalen==64){
      sha256_transform(ctx, ctx->data);
      ctx->bitlen += 512;
      ctx->datalen=0;
    }
  }
}

static void sha256_final(sha256_ctx *ctx, uint8_t out[32]){
  uint32_t i = ctx->datalen;

  // Pad
  if(ctx->datalen < 56){
    ctx->data[i++] = 0x80;
    while(i<56) ctx->data[i++] = 0x00;
  } else {
    ctx->data[i++] = 0x80;
    while(i<64) ctx->data[i++] = 0x00;
    sha256_transform(ctx, ctx->data);
    memset(ctx->data, 0, 56);
  }

  ctx->bitlen += (uint64_t)ctx->datalen * 8;

  // Append length (big-endian)
  ctx->data[63] = (uint8_t)(ctx->bitlen);
  ctx->data[62] = (uint8_t)(ctx->bitlen >> 8);
  ctx->data[61] = (uint8_t)(ctx->bitlen >> 16);
  ctx->data[60] = (uint8_t)(ctx->bitlen >> 24);
  ctx->data[59] = (uint8_t)(ctx->bitlen >> 32);
  ctx->data[58] = (uint8_t)(ctx->bitlen >> 40);
  ctx->data[57] = (uint8_t)(ctx->bitlen >> 48);
  ctx->data[56] = (uint8_t)(ctx->bitlen >> 56);

  sha256_transform(ctx, ctx->data);

  for(i=0;i<8;i++){
    out[i*4+0] = (uint8_t)(ctx->state[i] >> 24);
    out[i*4+1] = (uint8_t)(ctx->state[i] >> 16);
    out[i*4+2] = (uint8_t)(ctx->state[i] >> 8);
    out[i*4+3] = (uint8_t)(ctx->state[i]);
  }
}

static void hex32(const uint8_t in[32], char out[65]){
  static const char *h="0123456789abcdef";
  for(int i=0;i<32;i++){
    out[i*2+0]=h[(in[i]>>4)&0xF];
    out[i*2+1]=h[in[i]&0xF];
  }
  out[64]=0;
}
/* --------------------------------------------------------------------- */

static inline uint64_t splitmix64(uint64_t *x){
  uint64_t z = (*x += 0x9e3779b97f4a7c15ULL);
  z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
  z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
  return z ^ (z >> 31);
}

static inline ax_scalar_t as_scalar(uint64_t u){
  // map u -> signed int64 space deterministically
  return (ax_scalar_t)(int64_t)u;
}

static void feed_u64(sha256_ctx *h, uint64_t v){
  uint8_t b[8];
  // canonical little-endian
  for(int i=0;i<8;i++) b[i]=(uint8_t)(v>>(8*i));
  sha256_update(h,b,8);
}
static void feed_u32(sha256_ctx *h, uint32_t v){
  uint8_t b[4];
  for(int i=0;i<4;i++) b[i]=(uint8_t)(v>>(8*i));
  sha256_update(h,b,4);
}

int main(void){
  // FIX: previous "0xAX0ULL" was invalid. Use a stable numeric seed:
  uint64_t seed = 0xA10ULL + 0x123456789abcdef0ULL;

  sha256_ctx H;
  sha256_init(&H);

  // Deterministic suite size (keep stable once published)
  const int N = 200000;

  for(int i=0;i<N;i++){
    ax_status_t st = 0;

    // Inputs
    ax_scalar_t a = as_scalar(splitmix64(&seed));
    ax_scalar_t b = as_scalar(splitmix64(&seed));
    ax_scalar_t x = as_scalar(splitmix64(&seed));
    ax_scalar_t theta = (ax_scalar_t)((int64_t)(splitmix64(&seed) | 1ULL)); // avoid 0
    uint64_t cap = (splitmix64(&seed) % 128ULL) + 1ULL;                    // 1..128

    // Ops (K0 arithmetic, status via pointer)
    ax_scalar_t r_add = ax_add_sat(a, b, &st);
    ax_scalar_t r_mul = ax_mul_normative(a, b, &st);

    /* CORRECTIF (review 2026-06) : 'emit' etait declare deux fois (uint64_t puis
       uint32_t) -> erreur de compilation. L'API de reference (ax.c top-level) est
       ax_emit_o1(x, theta, cap, &emit, &st) et renvoie x_new. */
    uint64_t emit = 0;
    ax_scalar_t x2 = ax_emit_o1(x, theta, cap, &emit, &st);


    // Canonical transcript bytes
    feed_u64(&H, (uint64_t)r_add);
    feed_u64(&H, (uint64_t)r_mul);
    feed_u64(&H, (uint64_t)x2);
    feed_u64(&H, (uint64_t)emit);
    feed_u32(&H, (uint32_t)st);
  }

  uint8_t dig[32];
  sha256_final(&H, dig);

  char hex[65];
  hex32(dig, hex);

  printf("AX_K0_TEST_SHA256=%s\n", hex);
  return 0;
}
