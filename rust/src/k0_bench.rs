//! K0 benchmark — ns/op comparison: float64 vs i64 simple vs K0 normative
//! Uses std::hint::black_box to prevent loop elimination.

use std::time::Instant;
use std::hint::black_box;
use k0::{k0_mul_normative, splitmix64};

const N_OPS:  usize = 1_000_000;
const N_REPS: usize = 50;

#[inline(never)]
fn mul_simple(a: i64, b: i64) -> i64 {
    (((a as i128) * (b as i128)) >> 32) as i64
}

fn make_inputs(seed: u64) -> (Vec<i64>, Vec<i64>) {
    let mut seed = seed;
    let av: Vec<i64> = (0..N_OPS).map(|_| splitmix64(&mut seed) as i64).collect();
    let bv: Vec<i64> = (0..N_OPS).map(|_| splitmix64(&mut seed) as i64).collect();
    (av, bv)
}

fn run_bench<F: Fn(i64, i64) -> i64>(label: &str, f: F, av: &[i64], bv: &[i64], baseline: f64) {
    let mut times = vec![0.0f64; N_REPS];
    for rep in 0..N_REPS {
        let t0 = Instant::now();
        let mut acc: i64 = black_box(av[0]);
        for i in 0..N_OPS {
            acc = black_box(f(black_box(av[i] ^ acc), black_box(bv[i])));
        }
        let _ = black_box(acc);
        times[rep] = t0.elapsed().as_nanos() as f64 / N_OPS as f64;
    }
    let mean = times.iter().sum::<f64>() / N_REPS as f64;
    let std  = (times.iter().map(|t| (t - mean).powi(2)).sum::<f64>() / N_REPS as f64).sqrt();
    println!("  {:<38}: {:5.2} +-{:.2} ns/op  [x{:.2} vs f64]", label, mean, std, mean / baseline);
}

fn bench_float64(seed: u64) -> f64 {
    let mut seed = seed;
    let av: Vec<f64> = (0..N_OPS).map(|_| splitmix64(&mut seed) as f64 * 1e-18).collect();
    let bv: Vec<f64> = (0..N_OPS).map(|_| splitmix64(&mut seed) as f64 * 1e-18).collect();
    let mut times = vec![0.0f64; N_REPS];
    for rep in 0..N_REPS {
        let t0 = Instant::now();
        let mut acc: f64 = black_box(av[0]);
        for i in 0..N_OPS {
            acc = black_box((black_box(av[i]) + acc) * black_box(bv[i]));
        }
        let _ = black_box(acc);
        times[rep] = t0.elapsed().as_nanos() as f64 / N_OPS as f64;
    }
    let mean = times.iter().sum::<f64>() / N_REPS as f64;
    let std  = (times.iter().map(|t| (t - mean).powi(2)).sum::<f64>() / N_REPS as f64).sqrt();
    println!("  {:<38}: {:5.2} +-{:.2} ns/op  [baseline]", "float64 mul", mean, std);
    mean
}

fn main() {
    println!("AX K0 Cost Benchmark (Rust --release) -- {} ops x {} reps\n", N_OPS, N_REPS);
    let seed = 0x123456789abce900u64;
    let (av, bv) = make_inputs(seed);
    let baseline = bench_float64(seed);
    run_bench("K0 mul_simple (no RNE)", |a, b| mul_simple(a, b), &av, &bv, baseline);
    run_bench("K0 mul_normative (GRS+RNE)", |a, b| {
        let mut st: u8 = 0;
        k0_mul_normative(a, b, &mut st)
    }, &av, &bv, baseline);
}
