"""Debug patch for P3-4 (T4): let HotSpot write its grid-model matrices.

If the environment variable LTP_DUMP_DIR is set, the first transient step of the grid model
(SuperLU build) writes to that folder:
  G_csc.txt  the conductance matrix G (compressed sparse columns: n nnz, colptr, rowind value)
  C.txt      the diagonal capacitance matrix C
  P.txt      the power vector P of that step (node powers, including the ambient terms)
HotSpot's transient step solves (C/h + G) T_new = C/h T_old + P, so these three determine the
whole discrete-time system. Only used for the separate ~/projects/HotSpot-dump build.

usage: python3 patch_dump.py <path/to/temperature_grid.c>
"""
import sys

DUMP = r'''
  {
    /* LTP dump patch (P3-4): write G, C and P once */
    static int ltp_dumped = 0;
    char *ltp_dir = getenv("LTP_DUMP_DIR");
    if (ltp_dir && !ltp_dumped) {
      char fn[2048];
      FILE *f;
      int ii;
      NCformat *S = (NCformat *) G->Store;
      double *gv = (double *) S->nzval;
      sprintf(fn, "%s/G_csc.txt", ltp_dir);
      f = fopen(fn, "w");
      fprintf(f, "%d %d\n", G->ncol, S->nnz);
      for (ii = 0; ii <= G->ncol; ii++) fprintf(f, "%d\n", S->colptr[ii]);
      for (ii = 0; ii < S->nnz; ii++) fprintf(f, "%d %.17g\n", S->rowind[ii], gv[ii]);
      fclose(f);
      sprintf(fn, "%s/C.txt", ltp_dir);
      f = fopen(fn, "w");
      for (ii = 0; ii < C->n; ii++) fprintf(f, "%.17g\n", C->vals[ii]);
      fclose(f);
      sprintf(fn, "%s/P.txt", ltp_dir);
      f = fopen(fn, "w");
      for (ii = 0; ii < C->n; ii++) fprintf(f, "%.17g\n", P[ii]);
      fclose(f);
      ltp_dumped = 1;
    }
  }
  backward_euler(G, C, T, P, &h, T);'''

path = sys.argv[1]
src = open(path, newline="").read()
anchor = "  backward_euler(G, C, T, P, &h, T);"
if src.count(anchor) != 1:
    sys.exit(f"expected one backward_euler call, found {src.count(anchor)}")
src = src.replace(anchor, DUMP.lstrip("\n"))
if "#include <stdlib.h>" not in src:
    src = "#include <stdlib.h>\n" + src
open(path, "w", newline="").write(src)
print("dump patch applied")
