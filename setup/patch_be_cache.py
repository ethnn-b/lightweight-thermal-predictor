"""Speed patch for HotSpot's grid-model transient solver (SuperLU build).

Stock HotSpot does one backward-Euler step per sampling interval and calls dgssv each time,
i.e. it re-factorises A = C/h + G at every step although A only depends on h. This rewrites
backward_euler() in RCutil.c to factorise once per step size and then reuse L, U with dgstrs.
Same equations, same results (checked in experiments/P0-4_infrastructure), ~100x faster.

usage: python3 patch_be_cache.py <path/to/RCutil.c>
"""
import re
import sys

NEW_FUNC = r'''double backward_euler(SuperMatrix *G, diagonal_matrix_t *C, double *T, double *P, double *h, double *Tout)
{
  /* LTP patch: factorise A = C/h + G once per step size h, then reuse L and U. */
  static int ready = 0;
  static double cached_h = -1.0;
  static SuperMatrix L, U, *A = NULL;
  static int *perm_r = NULL, *perm_c = NULL;
  superlu_options_t options;
  SuperLUStat_t stat;
  SuperMatrix B;
  DNformat *Bstore;
  double *dp;
  int i, info, n = C->n;

  StatInit(&stat);
  if (build_B_matrix(C, T, P, *h, &B) != 1)
    fatal("In backward_euler(): Failed to build B matrix\n");

  if (!ready || *h != cached_h) {
    if (ready) {
      Destroy_CompCol_Matrix(A);
      Destroy_SuperNode_Matrix(&L);
      Destroy_CompCol_Matrix(&U);
    } else {
      if ( !(perm_r = intMalloc(n)) ) fatal("Malloc fails for perm_r[].\n");
      if ( !(perm_c = intMalloc(n)) ) fatal("Malloc fails for perm_c[].\n");
      A = calloc(1, sizeof(SuperMatrix));
    }
    if (build_A_matrix(G, C, *h, A) != 1)
      fatal("In backward_euler(): Failed to build A matrix\n");
    set_default_options(&options);
    dgssv(&options, A, perm_c, perm_r, &L, &U, &B, &stat, &info);
    ready = 1;
    cached_h = *h;
  } else {
    dgstrs(NOTRANS, &L, &U, perm_c, perm_r, &B, &stat, &info);
  }
  if (info != 0)
    fatal("In backward_euler(): SuperLU failed\n");

  Bstore = (DNformat *) B.Store;
  dp = (double *) Bstore->nzval;
  for (i = 0; i < n; i++)
    Tout[i] = dp[i];

  Destroy_SuperMatrix_Store(&B);
  free_dvector(dp);
  StatFree(&stat);
  return *h;
}
#endif

/* core of the 4th order Runge-Kutta method'''

src_path = sys.argv[1]
src = open(src_path, newline='').read()
pattern = re.compile(r'double backward_euler\(SuperMatrix \*G.*?\n#endif\n\n/\* core of the 4th order Runge-Kutta method',
                     re.S)
if 'LTP patch' in src:
    sys.exit('already patched')
new, count = pattern.subn(lambda m: NEW_FUNC, src)
if count != 1:
    sys.exit(f'expected one backward_euler() definition, found {count}')
open(src_path, 'w', newline='').write(new)
print('backward_euler() patched')
