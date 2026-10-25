/*
 * Calculate the factorial of n
 */
int factorial(int n) {
  // check validity
  assert(n >= 0);
  // base case
  if ((n == 1) || (n == 0)) {
      return 1;
  }
  // other cases
  return n * factorial(n - 1);
}
