/* Stage 1 C ABI smoke — link against karmazyn_substrate (no Python).
 *
 * From native/karmazyn_substrate after `cargo build --release`:
 *   gcc ../c_smoke/stage1_c_smoke.c -I include -L target/release \
 *       -lkarmazyn_substrate -o target/release/stage1_c_smoke.exe
 *   set PATH=target\release;%PATH%
 *   target\release\stage1_c_smoke.exe
 *
 * Or: .\native\stage1_verify.ps1
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "karmazyn_substrate.h"

static void die(const char *msg) {
    fprintf(stderr, "FAIL: %s\n", msg);
    exit(1);
}

int main(void) {
    const char *ver = ksub_version();
    printf("=== Stage 1 C ABI smoke ===\n");
    printf("  version: %s\n", ver ? ver : "(null)");

    uint64_t h = ksub_store_new(1);
    if (h == 0) die("ksub_store_new");

    /* orphan vacuum: unreachable + cool → GC */
    uint32_t orphan = ksub_atom_new(h, "var", "orphan", 50.0);
    if (orphan == UINT32_MAX) die("atom_new orphan");
    ksub_settle(h, 80);
    if (ksub_has_atom(h, orphan)) die("orphan should be vacuumed");
    printf("  [ OK ] orphan vacuum via C ABI\n");

    /* root retains TOMB */
    uint32_t root = ksub_bubble_new(h, "root", -1);
    if (root == UINT32_MAX) die("bubble_new");
    ksub_set_root(h, root);
    uint32_t keep = ksub_atom_new(h, "var", "keep", 50.0);
    if (keep == UINT32_MAX) die("atom_new keep");
    if (!ksub_bind(h, root, "keep", keep)) die("bind");
    ksub_settle(h, 80);
    if (!ksub_has_atom(h, keep)) die("rooted atom vanished");
    if (ksub_atom_is_dead(h, keep) != 1) die("expected TOMB");
    printf("  [ OK ] root retains TOMB\n");

    ksub_tick(h);

    KSubStats st;
    memset(&st, 0, sizeof(st));
    if (!ksub_stats(h, &st)) die("stats");
    printf(
        "  stats: total=%llu reaped=%llu retained_tomb=%llu bubbles=%llu\n",
        (unsigned long long)st.total,
        (unsigned long long)st.reaped,
        (unsigned long long)st.retained_tomb,
        (unsigned long long)st.bubbles
    );

    ksub_store_free(h);
    printf("=== STAGE1_C_OK ===\n");
    return 0;
}
