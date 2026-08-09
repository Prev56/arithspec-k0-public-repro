/* ax_bench.c — Benchmark : coût marginal GRS+RNE vs multiply simple en C
 *
 * Compare :
 *   A) mul_normative (GRS+RNE via __int128, conforme K0-Full)
 *   B) mul_simple    (décalage pur, pas de rounding)
 *   C) float64 mul   (IEEE-754 double)
 *   D) float32 mul   (IEEE-754 float)
 *
 * N_REPS = 50 répétitions de N_OPS opérations chacune.
 * Anti-optimization : accumulation de r dans un accumulateur volatil.
 */
#define _POSIX_C_SOURCE 200809L
#include "ax.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <time.h>
#include <string.h>

#define N_OPS  1000000
#define N_REPS 50
#define N_WARMUP 5

static inline uint64_t splitmix64(uint64_t *x){
  uint64_t z = (*x += 0x9e3779b97f4a7c15ULL);
  z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
  z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
  return z ^ (z >> 31);
}

/* Non-normative : Q32.32 mul, simple right-shift (no GRS) */
static inline int64_t mul_simple(int64_t a, int64_t b) {
    __int128 p = (__int128)a * (__int128)b;
    return (int64_t)(p >> 32);
}

/* Normative : GRS+RNE via __int128 (K0-Full) */
static inline int64_t mul_normative_inline(int64_t a, int64_t b) {
    __int128 P = (__int128)a * (__int128)b;
    __int128 Q = P >> 32;
    uint32_t low = (uint32_t)(((__uint128_t)P) & 0xFFFFFFFFu);
    uint32_t g = (low >> 31) & 1u;
    uint32_t r = (low >> 30) & 1u;
    uint32_t s = (low & 0x3FFFFFFFu) ? 1u : 0u;
    if (g && (r || s || ((uint32_t)Q & 1u))) Q++;
    /* saturation */
    if (Q > (int64_t)0x7FFFFFFFFFFFFFFFLL) return (int64_t)0x7FFFFFFFFFFFFFFFLL;
    if (Q < (int64_t)0x8000000000000000LL) return (int64_t)0x8000000000000000LL;
    return (int64_t)Q;
}

static double now_sec(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

/* Statistiques */
static double _mean(double *v, int n) {
    double s=0; for(int i=0;i<n;i++) s+=v[i]; return s/n;
}
static double _std(double *v, int n) {
    double m=_mean(v,n), s=0;
    for(int i=0;i<n;i++) s+=(v[i]-m)*(v[i]-m);
    return n>1 ? __builtin_sqrt(s/(n-1)) : 0.0;
}

int main(void) {
    /* Pré-générer les paires d'opérandes */
    int64_t *A = malloc(N_OPS * sizeof(int64_t));
    int64_t *B = malloc(N_OPS * sizeof(int64_t));
    float   *FA = malloc(N_OPS * sizeof(float));
    float   *FB = malloc(N_OPS * sizeof(float));
    double  *DA = malloc(N_OPS * sizeof(double));
    double  *DB = malloc(N_OPS * sizeof(double));

    uint64_t seed = 0xdeadbeef12345678ULL;
    for(int i=0;i<N_OPS;i++){
        A[i] = (int64_t)splitmix64(&seed);
        B[i] = (int64_t)splitmix64(&seed);
        FA[i] = (float)A[i] / (float)(1LL<<32);
        FB[i] = (float)B[i] / (float)(1LL<<32);
        DA[i] = (double)A[i] / (double)(1LL<<32);
        DB[i] = (double)B[i] / (double)(1LL<<32);
    }

    double t_norm[N_REPS], t_simp[N_REPS], t_f32[N_REPS], t_f64[N_REPS];
    volatile int64_t acc_n=1, acc_s=1;
    volatile double acc_f64=0.0;
    volatile float acc_f32=0.0f;

    /* Warmup */
    for(int w=0;w<N_WARMUP;w++){
        for(int i=0;i<N_OPS;i++) acc_n = mul_normative_inline(A[i] ^ acc_n, B[i]);
        for(int i=0;i<N_OPS;i++) acc_s = mul_simple(A[i] ^ acc_s, B[i]);
    }

    /* Bench mul_normative */
    acc_n = 1;
    for(int r=0;r<N_REPS;r++){
        double t0 = now_sec();
        for(int i=0;i<N_OPS;i++) acc_n = mul_normative_inline(A[i] ^ acc_n, B[i]);
        t_norm[r] = now_sec() - t0;
    }

    /* Bench mul_simple */
    acc_s = 1;
    for(int r=0;r<N_REPS;r++){
        double t0 = now_sec();
        for(int i=0;i<N_OPS;i++) acc_s = mul_simple(A[i] ^ acc_s, B[i]);
        t_simp[r] = now_sec() - t0;
    }

    /* Bench float64 */
    acc_f64 = 1.0;
    for(int r=0;r<N_REPS;r++){
        double t0 = now_sec();
        for(int i=0;i<N_OPS;i++) acc_f64 = DA[i] * DB[i] + acc_f64 * 1e-18;
        t_f64[r] = now_sec() - t0;
    }

    /* Bench float32 */
    acc_f32 = 1.0f;
    for(int r=0;r<N_REPS;r++){
        double t0 = now_sec();
        for(int i=0;i<N_OPS;i++) acc_f32 = FA[i] * FB[i] + acc_f32 * 1e-18f;
        t_f32[r] = now_sec() - t0;
    }

    double m_n  = _mean(t_norm,N_REPS), s_n  = _std(t_norm,N_REPS);
    double m_s  = _mean(t_simp,N_REPS), s_s  = _std(t_simp,N_REPS);
    double m_f64= _mean(t_f64, N_REPS), s_f64= _std(t_f64, N_REPS);
    double m_f32= _mean(t_f32, N_REPS), s_f32= _std(t_f32, N_REPS);

    printf("AX K0 Cost Benchmark — %d ops × %d reps\n\n", N_OPS, N_REPS);
    printf("  %-25s : %7.2f ± %5.2f ns/op  [baseline]\n",
           "float64 mul", m_f64/N_OPS*1e9, s_f64/N_OPS*1e9);
    printf("  %-25s : %7.2f ± %5.2f ns/op  [×%.2f vs f64]\n",
           "float32 mul", m_f32/N_OPS*1e9, s_f32/N_OPS*1e9, m_f32/m_f64);
    printf("  %-25s : %7.2f ± %5.2f ns/op  [×%.2f vs f64]\n",
           "K0 mul_simple (no RNE)", m_s/N_OPS*1e9, s_s/N_OPS*1e9, m_s/m_f64);
    printf("  %-25s : %7.2f ± %5.2f ns/op  [×%.2f vs f64, +%.1f%% vs simple]\n",
           "K0 mul_normative (GRS+RNE)", m_n/N_OPS*1e9, s_n/N_OPS*1e9,
           m_n/m_f64, (m_n/m_s - 1.0)*100.0);

    printf("\n  Anti-optimization sinks: %lld %lld %f %f\n",
           (long long)acc_n, (long long)acc_s, (double)acc_f64, (double)acc_f32);
    printf("\n  SURCOÛT NORMATIF C (GRS+RNE vs simple) : +%.1f%%\n", (m_n/m_s-1.0)*100.0);
    printf("  SURCOÛT NORMATIF C (GRS+RNE vs float64) : ×%.2f\n", m_n/m_f64);

    free(A); free(B); free(FA); free(FB); free(DA); free(DB);
    return 0;
}
