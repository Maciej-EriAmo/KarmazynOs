# Stage 2 — thermal × reach law (same as stage1 C smoke / golden_txreach)
# Host decay ~0.92; settle 80 → TOMB; orphan vacuums; rooted retains TOMB.
#
#   karmazyn_shell examples/lifecycle.ksh
# (cwd = repo root when run from stage2_verify)

echo === orphan vacuum ===
atom var orphan 50
assert has 0
settle 80
assert nohas 0
assert stats reaped ge 1

echo === root retains TOMB ===
atom var keep 50
bubble r
root 0
bind 0 k 1
assert lookup 0 k 1
settle 80
assert has 1
assert dead 1
assert stats retained ge 1

echo === unroot then reap ===
unroot 0
assert noroot 0
settle 4
assert nohas 1

echo lifecycle_ok
quit
