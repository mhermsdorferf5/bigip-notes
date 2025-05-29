# DNS TTL Workaround

There's a bug in some versions of bind where Resource Records (RRs) with a TTL of 0 are cached for however long we are currently away from the unix epoc (as of 2025, 55 years).

That bug is documented here: https://gitlab.isc.org/isc-projects/bind9/-/issues/5094

## F5 BIG-IP Fix

F5 DNS Cache will respond with DNS TTL zero both if it receives a DNS TTL of zero from the upstream DNS server and if it's DNS TTL cache has reached zero but the record has not yet been cleared out of cache.  This is documented here: https://cdn.f5.com/product/bugtracker/ID741203.html

We can however, use an iRule to update any DNS TTL from zero to one in order to prevent triggering the bind bug.

### iRule

```tcl
when DNS_RESPONSE {
    foreach rr [DNS::answer] {
        if { [DNS::ttl $rr] == 0 } {
            DNS::ttl $rr 1
        }
    }
}
```

### iRule Performance

Note all of this is approximant, based on lots of assumptions real world results will be different.

Processor CPU in Ghz:
2,200,000,000
(Note the i4800, has a 2.2ghz processor.)

If we assume the iRule has an average run cpu cycles of 71,600 cycles.  (As tested in the lab, see assumptions below, final testing results ended up consistently faster at 21,600 cycles, but leaving the higher number to be conservative.)

If we further assume we are processing around 1,000 DNS Queries per second:

(71,600/2,200,000,000)*1000 = 3.25% increase in CPU usage per every 1000 DNS responses per second.

The final assumption is that this will be RR set dependent, my testing is based on an average of 2.5 RRs per DNS request.

## Failed Optimizations

List of failed optimization attempts, documented so that clever folks don't waste time trying them again.

Command used for performance testing:
```bash
dnsperf -s <f5-vip> -n 1000 -Q 100 -d dns-tt-test.dnsperf
```

* All tests done with a set of queries to records as follows:
  * 2 records with 1 RR with authoritative TTLs set to 1.
  * 2 records with 1 RR with authoritative TTLs set to 0.
  * 2 records with 4 RRs with authoritative TTLs set to 1.
  * 2 records with 4 RRs with authoritative TTLs set to 0.
  * 2 records with 10 RRs with authoritative TTLs set to 1.
  * 2 records with 10 RRs with authoritative TTLs set to 0.
  * A record with 1 RR with authoritative TTL set to 300.
  * A record with 1 RR with authoritative TTL set to 60.

#### iRule 1, most performant

```tcl
when DNS_RESPONSE {
    foreach rr [DNS::answer] {
        if { [DNS::ttl $rr] == 0 } {
            DNS::ttl $rr 1
        }
    }
}
```

Performance Results:
```
---------------------------------------------
Ltm::Rule Event: dns-reset-ttl-0:DNS_RESPONSE
---------------------------------------------
Priority                    500
Executions
  Total                   14.0K
  Failures                    0
  Aborts                      0
CPU Cycles on Executing
  Average                 21.6K
  Maximum                165.2K
  Minimum                     0
```

### iRule 2

Attempt at more performance by simply incrementing every TTL by 1

```tcl
when DNS_RESPONSE {
    foreach rr [DNS::answer] {
        DNS::ttl $rr [expr [DNS::ttl $rr] + 1]
    }
}
```

Performance Results:
```
---------------------------------------------
Ltm::Rule Event: dns-reset-ttl-0:DNS_RESPONSE
---------------------------------------------
Priority                   500
Executions
  Total                  14.0K
  Failures                   0
  Aborts                     0
CPU Cycles on Executing
  Average                35.8K
  Maximum                 2.9M
  Minimum                    0
```

#### iRule 3

Attempt at optimization, by using lsearch to only loop into RRs with a TTL of 0.

```tcl
when DNS_RESPONSE {
    foreach rr [lsearch -inline -all [DNS::answer] 0] {
        if { [DNS::ttl $rr] == 0 } {
            DNS::ttl $rr 1
        }
    }
}
```

Performance Results:
```
---------------------------------------------
Ltm::Rule Event: dns-reset-ttl-0:DNS_RESPONSE
---------------------------------------------
Priority                    500
Executions
  Total                   14.0K
  Failures                    0
  Aborts                      0
CPU Cycles on Executing
  Average                 50.7K
  Maximum                226.1K
  Minimum                     0
```

#### iRule 4

Another attempt at optimization, by using lsearch to only loop into RRs with a TTL of 0.
I have no idea how this turned out slightly slower than iRule #3...

```tcl
when DNS_RESPONSE {
    foreach rr [lsearch -inline -all [DNS::answer] 0] {
        DNS::ttl $rr 1
    }
}
```

Performance Results:
```
---------------------------------------------
Ltm::Rule Event: dns-reset-ttl-0:DNS_RESPONSE
---------------------------------------------
Priority                    500
Executions
  Total                   14.0K
  Failures                    0
  Aborts                      0
CPU Cycles on Executing
  Average                 52.2K
  Maximum                220.8K
  Minimum                     0
```
