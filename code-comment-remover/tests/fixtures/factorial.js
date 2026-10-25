/*
 * Calculate the factorial of n
 */
function factorial(n) {
  // check n is valid
  if (typeof n !== 'number' || !Number.isInteger(n) || n < 0) {
    throw new Error('n must be a non-negative integer');
  }
  // base case
  if ((n === 1) || (n === 0)) {
    return 1;
  }
  // other cases
  return n * factorial(n - 1)
}
