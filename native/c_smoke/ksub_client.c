/* Thin Tor A C client on ksub_* — more API surface than stage1_c_smoke.
 *
 * Build (from native/karmazyn_substrate after cargo build --release):
 *   gcc ../c_smoke/ksub_client.c -I include target/release/karmazyn_substrate.dll \
 *       -o target/release/ksub_client.exe
 *   set PATH=target\release;%PATH%
 *   ksub_client.exe
 *
 * Prefer linking the DLL path (not -l) so MinGW does not pick a stale .dll.a.
 * Or: .\native\stage1_verify.ps1
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "karmazyn_substrate.h"

static void die(const char *msg) {
    fprintf(stderr, "ksub_client FAIL: %s\n", msg);
    exit(1);
}

static void print_stats(uint64_t h, const char *tag) {
    KSubStats st;
    memset(&st, 0, sizeof(st));
    if (!ksub_stats(h, &st)) die("stats");
    printf(
        "  [%s] total=%llu alive=%llu dead=%llu reaped=%llu retained_tomb=%llu bubbles=%llu\n",
        tag,
        (unsigned long long)st.total,
        (unsigned long long)st.alive,
        (unsigned long long)st.dead,
        (unsigned long long)st.reaped,
        (unsigned long long)st.retained_tomb,
        (unsigned long long)st.bubbles
    );
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;

    const char *ver = ksub_version();
    printf("=== ksub_client (Tor A thin C) ===\n");
    printf("  ksub_version: %s\n", ver ? ver : "(null)");
    if (!ver || ver[0] == '\0') die("empty version");

    /* strdup / string_free pair (version itself is static — never free it) */
    char *vcopy = ksub_strdup(ver);
    if (!vcopy) die("ksub_strdup");
    if (strcmp(vcopy, ver) != 0) die("ksub_strdup content");
    ksub_string_free(vcopy);
    ksub_string_free(NULL); /* null-safe */
    printf("  [ OK ] ksub_strdup / ksub_string_free\n");

    uint64_t h = ksub_store_new(1);
    if (h == 0) die("ksub_store_new");

    /* value set/get */
    uint32_t a = ksub_atom_new(h, "var", "x", 80.0);
    if (a == UINT32_MAX) die("atom_new x");
    if (!ksub_atom_set_value(h, a, 0xC0FFEEu)) die("set_value");
    if (ksub_atom_value(h, a) != 0xC0FFEEu) die("get_value mismatch");
    printf("  [ OK ] atom value set/get\n");

    /* heat + T */
    if (!ksub_heat(h, a)) die("heat");
    double t = ksub_atom_t(h, a);
    if (!(t > 0.0)) die("atom_t after heat");
    if (!ksub_atom_set_t(h, a, 60.0)) die("set_t");
    if (ksub_atom_t(h, a) != 60.0) die("get_t mismatch");
    printf("  [ OK ] heat / T read-write\n");

    /* bubble + bind + lookup */
    uint32_t root = ksub_bubble_new(h, "cli_root", -1);
    if (root == UINT32_MAX) die("bubble_new");
    ksub_set_root(h, root);
    if (!ksub_bind(h, root, "x", a)) die("bind");
    int64_t looked = ksub_lookup(h, root, "x");
    if (looked < 0 || (uint32_t)looked != a) die("lookup");
    printf("  [ OK ] bind / lookup\n");

    ksub_tick(h);
    print_stats(h, "after tick");

    /* unbind + settle orphan path on a fresh atom */
    uint32_t orphan = ksub_atom_new(h, "var", "orphan", 40.0);
    if (orphan == UINT32_MAX) die("atom_new orphan");
    ksub_settle(h, 80);
    if (ksub_has_atom(h, orphan)) die("orphan should vacuum");
    printf("  [ OK ] settle vacuums unbound orphan\n");

    /* rooted atom survives settle */
    if (!ksub_has_atom(h, a)) die("rooted atom vanished");
    printf("  [ OK ] rooted atom retained\n");

    int64_t unbound = ksub_unbind(h, root, "x");
    if (unbound < 0) die("unbind");
    if (ksub_lookup(h, root, "x") >= 0) die("lookup after unbind should miss");
    printf("  [ OK ] unbind\n");

    print_stats(h, "final");
    ksub_store_free(h);
    printf("=== KSUB_CLIENT_OK ===\n");
    return 0;
}
