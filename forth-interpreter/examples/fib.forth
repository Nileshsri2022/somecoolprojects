: fib over over + ;  ( generate the next number in the Fibonacci sequence )

: fibn 10 1 do fib dup . loop ;

0 dup . 1 dup . fibn ( generate the next numbers )

cr
