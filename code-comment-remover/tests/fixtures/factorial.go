/*
 * Calculate the factorial of n
 */
package main

// factorial calculates the factorial of n.
func factorial(n int) int {
  // check validity
  if n == 0 || n == 1 {
    return 1
  }
  // other cases
  return n * factorial(n-1)
}

//go:generate echo hi
