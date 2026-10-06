# Cache Simulator (4-Way Set-Associative, LRU)

A small Python simulator of a CPU → Cache → DRAM memory system. It prints every memory request as a HIT or MISS, shows which block gets evicted, and ends with a dump of the cache contents.

## What it is

| Part | Details |
|------|---------|
| **DRAM** | 64 bytes, laid out as an 8x8 grid, 6-bit addresses (0x00–0x3F) |
| **Cache** | 16 blocks, 4-way set-associative (4 sets x 4 ways), block size 1 |
| **Address split** | `[ tag (4 bits) \| set index (2 bits) ]` |
| **Write policy** | Write-through, no-write-allocate (write misses go straight to DRAM) |
| **Replacement** | LRU: when a set is full, the least recently used block is evicted |

**How LRU works:** every access increments a clock. The line that was used gets stamped with the current clock value. On a full set, the line with the smallest stamp is evicted.

## Requirements

- Python 3.7+ (no extra packages needed)

## Run it

```bash
python cache_sim.py
```

On macOS/Linux you may need `python3` instead of `python`.

In VS Code, you can also open the file and click the ▶ **Run Python File** button.

## Example output

```
0x0 (000000, tag=0, set=0) READ  MISS -> fetched 10 from DRAM (way 0)
...
0x0 (000000, tag=0, set=0) READ  HIT  -> data 10 (way 0)
0x10 (010000, tag=4, set=0) READ  MISS  [LRU evict 0x4 from way 1] -> fetched 58 from DRAM (way 1)
...
Final Stats: 1 hits, 15 misses
```

## Try your own tests

- **Change the requests:** edit the `requests` list in `main()`. Each entry is `MemRequest(write, address, data)`, where `write` is 0 for read and 1 for write.
- **Change the cache shape:** set `WAYS` at the top of the file. `1` is direct-mapped, `4` is the default, and `16` is fully associative.
