#include <cstdint>
#include <vector>
#include <string>
#include <sstream>
#include <iomanip>
#include <iostream>
#include <cstdlib>

static const uint8_t AX_OK=0,AX_SATURATED=1,AX_TRUNCATED=2,AX_BURST_CROP=4,AX_INPUT_RANGE=8,AX_DIV_ZERO=16;

static int32_t clamp32(int64_t v, uint8_t& st){
    if(v>(int64_t)INT32_MAX){st|=AX_SATURATED;return INT32_MAX;}
    if(v<(int64_t)INT32_MIN){st|=AX_SATURATED;return INT32_MIN;}
    return (int32_t)v;
}
static int32_t add_sat(int32_t a,int32_t b,uint8_t& st){
    return clamp32((int64_t)a+(int64_t)b,st);
}
/* mul_normative: exact mirror of k0_lite.rs
   low_u32 = (p as u64) as u32  (two's complement bit pattern of lower 32 bits) */
static int32_t mul_norm(int32_t a,int32_t b,uint8_t& st){
    int64_t p=(int64_t)a*(int64_t)b;
    int64_t q=p>>16;
    uint32_t low_u32=(uint32_t)((uint64_t)p);
    uint32_t low16=low_u32&0xFFFF;
    uint32_t g=(low_u32>>15)&1, r=(low_u32>>14)&1;
    uint32_t s=(low_u32&0x3FFF)?1:0;
    if(low16) st|=AX_TRUNCATED;
    if(g&&(r||s||((q&1)!=0))) q+=1;
    return clamp32(q,st);
}
/* emit_o1: integer division model (exact mirror of k0_lite.rs) */
static int32_t emit_o1(int32_t x,int32_t theta,uint32_t emit_cap,uint32_t& emit_out,uint8_t& st){
    emit_out=0;
    if(theta<=0){st|=AX_DIV_ZERO;return x;}
    if(x<0){st|=AX_INPUT_RANGE;return x;}
    uint32_t em=(uint32_t)((int64_t)x/(int64_t)theta);
    if(em>emit_cap){st|=AX_BURST_CROP;em=emit_cap;}
    int64_t sub=(int64_t)em*(int64_t)theta;
    int32_t x_new=add_sat(x,-(int32_t)sub,st);
    emit_out=em;
    return x_new;
}
static uint64_t splitmix64(uint64_t& s){
    s+=0x9e3779b97f4a7c15ULL; uint64_t z=s;
    z=(z^(z>>30))*0xbf58476d1ce4e5b9ULL;
    z=(z^(z>>27))*0x94d049bb133111ebULL;
    return z^(z>>31);
}
/* Minimal SHA-256 */
static const uint32_t SK[64]={
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
};
static inline uint32_t rotr32(uint32_t x,int n){return(x>>n)|(x<<(32-n));}
static std::string sha256hex(const std::vector<uint8_t>& data){
    uint32_t h[8]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    std::vector<uint8_t> msg(data);
    msg.push_back(0x80);
    while(msg.size()%64!=56) msg.push_back(0);
    uint64_t bl=(uint64_t)data.size()*8;
    for(int i=7;i>=0;i--) msg.push_back((bl>>(i*8))&0xFF);
    for(size_t off=0;off<msg.size();off+=64){
        uint32_t w[64];
        for(int i=0;i<16;i++) w[i]=(uint32_t(msg[off+i*4])<<24)|(uint32_t(msg[off+i*4+1])<<16)|(uint32_t(msg[off+i*4+2])<<8)|msg[off+i*4+3];
        for(int i=16;i<64;i++){uint32_t s0=rotr32(w[i-15],7)^rotr32(w[i-15],18)^(w[i-15]>>3);uint32_t s1=rotr32(w[i-2],17)^rotr32(w[i-2],19)^(w[i-2]>>10);w[i]=w[i-16]+s0+w[i-7]+s1;}
        uint32_t a=h[0],b=h[1],cc=h[2],d=h[3],e=h[4],f=h[5],g=h[6],hh=h[7];
        for(int i=0;i<64;i++){uint32_t S1=rotr32(e,6)^rotr32(e,11)^rotr32(e,25);uint32_t ch=(e&f)^(~e&g);uint32_t t1=hh+S1+ch+SK[i]+w[i];uint32_t S0=rotr32(a,2)^rotr32(a,13)^rotr32(a,22);uint32_t maj=(a&b)^(a&cc)^(b&cc);uint32_t t2=S0+maj;hh=g;g=f;f=e;e=d+t1;d=cc;cc=b;b=a;a=t1+t2;}
        h[0]+=a;h[1]+=b;h[2]+=cc;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=hh;
    }
    std::ostringstream ss;
    for(int i=0;i<8;i++) for(int j=3;j>=0;j--) ss<<std::hex<<std::setw(2)<<std::setfill('0')<<((h[i]>>(j*8))&0xFF);
    return ss.str();
}
/* K0-Lite run: exact mirror of k0_lite_test.rs protocol */
static std::string k0run(int N){
    const uint64_t SEED=0x123456789abce900ULL;
    const uint32_t EMIT_CAP=15;
    const int32_t  THETA=1<<15;
    uint64_t rng=SEED;
    int32_t  acc=0;
    std::vector<uint8_t> buf; buf.reserve(N*14);
    auto w32=[&](int32_t v){uint32_t u=(uint32_t)v;buf.push_back(u&0xFF);buf.push_back((u>>8)&0xFF);buf.push_back((u>>16)&0xFF);buf.push_back((u>>24)&0xFF);};
    auto w16=[&](uint16_t v){buf.push_back(v&0xFF);buf.push_back((v>>8)&0xFF);};
    for(int i=0;i<N;i++){
        uint64_t ra=splitmix64(rng), rb=splitmix64(rng);
        /* wrapping_sub(0x007F_FFFF=8388607) — no wrap since inputs in [0,16777215] */
        int32_t a=(int32_t)(ra&0x00FFFFFFu)-8388607;
        int32_t b=(int32_t)(rb&0x00FFFFFFu)-8388607;
        uint8_t st=0;
        int32_t mac=mul_norm(a,b,st);
        int32_t add_val=add_sat(acc,mac,st);
        acc=add_val;
        uint32_t emit_out=0;
        /* Mirror Rust i32::abs() wrapping semantics (release mode):
           i32::MIN.abs() == i32::MIN (wrapping, stays negative).
           Using unsigned negation avoids C++ UB on INT32_MIN. */
        uint32_t uabs=(uint32_t)(add_val<0 ? -(uint32_t)add_val : (uint32_t)add_val);
        int32_t abs_add=(int32_t)uabs;
        int32_t v_new=emit_o1(abs_add,THETA,EMIT_CAP,emit_out,st);
        /* transcript: mac(4) add(4) emit_u16(2) v_new(4) = 14 bytes */
        w32(mac); w32(add_val); w16((uint16_t)emit_out); w32(v_new);
    }
    return sha256hex(buf);
}
int main(){
    std::string h1=k0run(200000), h2=k0run(200000);
    const std::string ref="e1606bef1b34afe155adeace4aae7fd2aa22f0236ada22a61dd71631baae050a";
    std::cout<<"AX_K0_LITE_CPP_RUN1="<<h1<<"\n";
    std::cout<<"AX_K0_LITE_CPP_RUN2="<<h2<<"\n";
    std::cout<<"RUN1_EQ_RUN2="<<(h1==h2?"true":"false")<<"\n";
    std::cout<<"MATCH_REF="<<(h1==ref?"true":"false")<<"\n";
    return (h1==h2 && h1==ref) ? 0 : 1;
}
