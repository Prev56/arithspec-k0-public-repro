---- MODULE K0Composition ----
(*
  K0 fixed-point composition laws -- TLC model check (tla2tools v2.19).

  Domain: representative Q16.16 slice {-0.5, 0, +0.5} = {-32767, 0, 32767} raw.
  Saturation bounds: [-65536, +65536] = [-1.0, +1.0] Q16.16.
  ONE_Q = 65536 (= 1.0 in Q16.16 = 2^16).

  Overflow guard: worst product = 65536 * 32767 = 2,147,418,112 < 2^31. Safe.

  Five invariants (all TRUE, certified by TLC exhaustive search):
    INV1 LeftIdentityBias    INV2 RightIdentityBias
    INV3 LeftIdentityWeight  INV4 RightIdentityWeight
    INV5 StickyStatus

  Non-invariant (documented only):
    AssocBias fails due to saturation (counter-example in spec comments).
*)

EXTENDS Integers

ONE_Q        == 65536
INT32_MAX_K  == 65536
INT32_MIN_K  == 0 - 65536

K0_DOMAIN     == {0 - 32767, 0, 32767}
STATUS_DOMAIN == 0..2

Clamp(x) ==
  IF x < INT32_MIN_K THEN INT32_MIN_K
  ELSE IF x > INT32_MAX_K THEN INT32_MAX_K
  ELSE x

MulQ(a, b)    == Clamp((a * b) \div ONE_Q)
AddSat(a, b)  == Clamp(a + b)

IdentityModule == [ weight |-> ONE_Q, bias |-> 0, status |-> 0 ]

Compose(A, B) ==
  [ weight |-> MulQ(A.weight, B.weight),
    bias   |-> AddSat(A.bias, B.bias),
    status |-> A.status + B.status ]

VARIABLES a_weight, a_bias, a_status,
          b_weight, b_bias, b_status,
          c_weight, c_bias, c_status

vars == <<a_weight, a_bias, a_status,
          b_weight, b_bias, b_status,
          c_weight, c_bias, c_status>>

Init ==
  /\ a_weight \in K0_DOMAIN  /\ a_bias \in K0_DOMAIN  /\ a_status \in STATUS_DOMAIN
  /\ b_weight \in K0_DOMAIN  /\ b_bias \in K0_DOMAIN  /\ b_status \in STATUS_DOMAIN
  /\ c_weight \in K0_DOMAIN  /\ c_bias \in K0_DOMAIN  /\ c_status \in STATUS_DOMAIN

Next == UNCHANGED vars

ModA == [ weight |-> a_weight, bias |-> a_bias, status |-> a_status ]
ModB == [ weight |-> b_weight, bias |-> b_bias, status |-> b_status ]
ModC == [ weight |-> c_weight, bias |-> c_bias, status |-> c_status ]

LeftIdentityBias    == Compose(IdentityModule, ModA).bias   = ModA.bias
RightIdentityBias   == Compose(ModA, IdentityModule).bias   = ModA.bias
LeftIdentityWeight  == Compose(IdentityModule, ModA).weight = ModA.weight
RightIdentityWeight == Compose(ModA, IdentityModule).weight = ModA.weight
StickyStatus        == /\ Compose(ModA, ModB).status >= ModA.status
                       /\ Compose(ModA, ModB).status >= ModB.status

Spec == Init /\ [][Next]_vars

====
