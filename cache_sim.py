"""
============================================================================
 SET-ASSOCIATIVE CACHE SIMULATOR (Write-Through, LRU Replacement)
============================================================================
 BIG PICTURE
   CPU  --->  Cache  --->  DRAM
   The CPU never talks to DRAM directly. Every request goes through the
   cache first. The cache answers quickly if it has the data (HIT) and
   goes to the slow DRAM only if it doesn't (MISS).

 SPECS
 • DRAM: 64 bytes (8x8 grid), accessed via 6-bit addresses (0 to 63).
 • Cache: 16 total blocks. Organized as a 4-Way Set-Associative cache.
          This means: 16 blocks / 4 ways = 4 Sets.
 • Address Split: [ Tag (4 bits) | Set Index (2 bits) ]
                  (No offset bits because block size = 1 byte)
 • Policy: Write-Through (writes go to Cache AND DRAM)
           No-Write-Allocate (write misses go straight to DRAM)
           LRU Replacement (Least Recently Used block is evicted)

 WHY SET-ASSOCIATIVE?
   A direct-mapped cache gives each address exactly ONE possible slot, so
   there is never a choice of what to evict and LRU is meaningless.
   With 4 ways, an address can go in any of 4 slots in its set, so when the
   set is full we must CHOOSE a victim. LRU makes that choice.
============================================================================
"""
from dataclasses import dataclass


# ----------------------------------------------------------------------------
# CONFIGURATION: change WAYS to experiment (1 = direct-mapped, 16 = fully
# associative). Everything else is calculated from it.
# ----------------------------------------------------------------------------
TOTAL_BLOCKS = 16
WAYS = 4
SETS = TOTAL_BLOCKS // WAYS          # 16 / 4 = 4 sets

# Number of address bits needed to pick a set. 4 sets -> 2 bits.
INDEX_BITS = (SETS - 1).bit_length()


# ----------------------------------------------------------------------------
# MEMORY REQUEST: the "message" passed between components (CPU, cache, DRAM).
# It mirrors the signals in the system diagram.
# ----------------------------------------------------------------------------
@dataclass
class MemRequest:
    """Represents the signals traveling on the memory bus."""
    write: int            # 0 = read, 1 = write
    address: int          # 6-bit DRAM address
    data_out: int = 0     # data being written (CPU/cache -> DRAM)
    data_in: int = 0      # data being read back (DRAM/cache -> CPU)


# ----------------------------------------------------------------------------
# DRAM: the slow, large main memory. It always has the correct data.
# ----------------------------------------------------------------------------
class DRAM:
    """Main memory: 8 rows x 8 columns."""

    def __init__(self):
        # Pre-fill each cell with a predictable number so results are easy
        # to verify (e.g. address 0 holds 10, address 1 holds 13, ...).
        self.cells = [
            [(r * 8 + c) * 3 + 10 for c in range(8)]
            for r in range(8)
        ]

    def access(self, req: MemRequest):
        # Decode the 6-bit address into a row and column:
        #   upper 3 bits = row, lower 3 bits = column
        row = req.address >> 3
        col = req.address & 0b111

        if req.write:
            self.cells[row][col] = req.data_out      # store new value
        else:
            req.data_in = self.cells[row][col]       # send value back


# ----------------------------------------------------------------------------
# CACHE LINE: one slot in the cache. Holds the three things a cache must track.
# ----------------------------------------------------------------------------
@dataclass
class CacheLine:
    """A single slot (way) inside a cache set."""
    valid: bool = False   # does this slot hold real data yet? (False at start)
    tag: int = 0          # identifies WHICH address is stored here
    data: int = 0         # the actual stored value
    last_used: int = 0    # timestamp of last use -> this is how LRU works


# ----------------------------------------------------------------------------
# CACHE: small, fast memory sitting between the CPU and DRAM.
# ----------------------------------------------------------------------------
class Cache:

    def __init__(self, dram: DRAM):
        self.dram = dram

        # 2D grid of lines: self.sets[set_number][way_number]
        # Think of it as 4 rows (sets), each with 4 slots (ways).
        self.sets = [
            [CacheLine() for _ in range(WAYS)]
            for _ in range(SETS)
        ]

        # A counter that goes up by 1 on every access. We stamp it onto a
        # line when it is used, so a SMALLER stamp means "used longer ago".
        self.clock = 0
        self.hits = 0
        self.misses = 0

    # ------------------------------------------------------------------
    # Helper Methods
    # ------------------------------------------------------------------

    def _find_hit(self, set_idx: int, tag: int) -> int:
        """Returns the way_index if there's a hit, otherwise None."""
        # Search every way in the set. A HIT needs BOTH:
        #   valid bit set (slot has real data) AND tag matches (right address)
        for way_idx, line in enumerate(self.sets[set_idx]):
            if line.valid and line.tag == tag:
                return way_idx

        return None

    def _find_victim(self, set_idx: int) -> int:
        """Find an empty slot or the least recently used slot."""
        # Step 1: use a free slot if there is one (nothing needs evicting).
        for way_idx, line in enumerate(self.sets[set_idx]):
            if not line.valid:
                return way_idx

        # Step 2: set is full, so evict the line with the SMALLEST
        # last_used value = the one untouched for the longest time (LRU).
        return min(
            range(WAYS),
            key=lambda w: self.sets[set_idx][w].last_used
        )

    def _update_lru(self, set_idx: int, way_idx: int):
        """Mark a cache line as recently used."""
        # Stamp the line with the current clock = "I was just used".
        self.sets[set_idx][way_idx].last_used = self.clock

    # ------------------------------------------------------------------
    # Main Access Logic: every CPU request enters here.
    # ------------------------------------------------------------------

    def access(self, cpu_req: MemRequest):

        self.clock += 1   # time moves forward by one tick per request

        # --------------------------------------------------------------
        # 1. Parse address: split into set index (low bits) and tag (high bits)
        #    Example: 0x14 = 010100 -> tag = 0101 (5), set = 00 (0)
        # --------------------------------------------------------------

        set_idx = cpu_req.address & (SETS - 1)    # which set to look in
        tag = cpu_req.address >> INDEX_BITS       # which address within it

        # --------------------------------------------------------------
        # 2. Check for hit: look through the ways of that one set only
        # --------------------------------------------------------------

        way_idx = self._find_hit(set_idx, tag)
        is_hit = way_idx is not None

        action = "WRITE" if cpu_req.write else "READ "
        result = "HIT " if is_hit else "MISS"

        # Using hex() and bin() (bin gives '0b101', so [2:] strips '0b' and
        # zfill(6) pads with zeros to a full 6-bit number)
        address_hex = hex(cpu_req.address)
        address_binary = bin(cpu_req.address)[2:].zfill(6)

        # Start building the line we print; the handlers add the rest.
        msg = (
            f"{address_hex} ({address_binary}, "
            f"tag={tag}, set={set_idx}) "
            f"{action} {result}"
        )

        # --------------------------------------------------------------
        # 3. Handle hit or miss
        # --------------------------------------------------------------

        if is_hit:
            msg += self._handle_hit(
                cpu_req,
                set_idx,
                way_idx
            )
        else:
            msg += self._handle_miss(
                cpu_req,
                set_idx,
                tag
            )

        print(msg)

    def _handle_hit(
        self,
        cpu_req: MemRequest,
        set_idx: int,
        way_idx: int
    ) -> str:
        """The data is in the cache. Fast path, no DRAM read needed."""

        self.hits += 1

        line = self.sets[set_idx][way_idx]

        # Any hit (read OR write) counts as a "use", so refresh its LRU stamp.
        self._update_lru(set_idx, way_idx)

        if not cpu_req.write:

            # READ HIT: just hand the cached value to the CPU.
            cpu_req.data_in = line.data

            return (
                f" -> data {cpu_req.data_in} "
                f"(way {way_idx})"
            )

        else:

            # WRITE HIT: update the cache copy AND send the write to DRAM.
            # That is "write-through": DRAM is never out of date.
            line.data = cpu_req.data_out

            self.dram.access(
                MemRequest(
                    1,
                    cpu_req.address,
                    cpu_req.data_out
                )
            )

            return (
                f" -> wrote {cpu_req.data_out} "
                f"to cache and DRAM (way {way_idx})"
            )

    def _handle_miss(
        self,
        cpu_req: MemRequest,
        set_idx: int,
        tag: int
    ) -> str:
        """The data is NOT in the cache. Must go to DRAM."""

        self.misses += 1

        # --------------------------------------------------------------
        # READ MISS: fetch from DRAM, store it in the cache, return it.
        # --------------------------------------------------------------

        if not cpu_req.write:

            # Ask DRAM for the value.
            dram_req = MemRequest(
                0,
                cpu_req.address
            )

            self.dram.access(dram_req)

            # Decide where to put it: a free slot, or evict the LRU line.
            way_idx = self._find_victim(set_idx)

            line = self.sets[set_idx][way_idx]

            # If the slot was already in use, we are evicting something.
            # Rebuild its full address from (tag, set) so we can report it.
            if line.valid:

                evicted_addr = (
                    (line.tag << INDEX_BITS)
                    | set_idx
                )

                msg = (
                    f"  [LRU evict {hex(evicted_addr)} "
                    f"from way {way_idx}]"
                )

            else:
                msg = ""

            # Install new data: set valid bit, tag, and data in the slot.
            line.valid = True
            line.tag = tag
            line.data = dram_req.data_in

            # The newly loaded line is now the MOST recently used.
            self._update_lru(
                set_idx,
                way_idx
            )

            # Finally pass the data on to the CPU.
            cpu_req.data_in = dram_req.data_in

            return (
                msg +
                f" -> fetched {cpu_req.data_in} "
                f"from DRAM (way {way_idx})"
            )

        # --------------------------------------------------------------
        # WRITE MISS: send the write straight to DRAM and do NOT bring the
        # block into the cache ("no-write-allocate"). Nothing in the cache
        # changes, so LRU is untouched too.
        # --------------------------------------------------------------

        else:

            self.dram.access(
                MemRequest(
                    1,
                    cpu_req.address,
                    cpu_req.data_out
                )
            )

            return (
                f" -> wrote {cpu_req.data_out} "
                f"to DRAM only (no-write-allocate)"
            )

    def dump(self):
        """Print cache contents."""
        # Shows each set with its lines sorted from most to least recently
        # used, so the LAST item in each row is the next eviction candidate.

        print(
            "\n--- Cache Contents "
            "(Most Recent -> Least Recent) ---"
        )

        for set_idx, ways in enumerate(self.sets):

            sorted_ways = sorted(
                range(WAYS),
                key=lambda w: ways[w].last_used,
                reverse=True
            )

            items = []

            for w in sorted_ways:

                line = ways[w]

                if line.valid:

                    # Rebuild the full address from tag + set index.
                    addr = (
                        (line.tag << INDEX_BITS)
                        | set_idx
                    )

                    # Using hex() here too
                    address_hex = hex(addr)

                    items.append(
                        f"[{address_hex}={line.data}] "
                        f"(LRU:{line.last_used})"
                    )

                else:

                    items.append("[EMPTY]")

            print(
                f"Set {set_idx}: "
                + "  ".join(items)
            )


# ----------------------------------------------------------------------------
# CPU / TEST DRIVER: generates the memory requests (max 16).
# With 4 sets x 4 ways, address % 4 picks the set:
#   set 0 -> 0x00 0x04 0x08 0x0C 0x10 ...
#   set 1 -> 0x01 0x05 0x09 0x0D 0x11 ...
#   set 2 -> 0x02 0x06 0x0A 0x0E 0x12 ...
# Plan: fill sets 0, 1 and 2 completely (12 requests), leave set 3 empty,
# then use the last 4 requests to force several LRU evictions.
# ----------------------------------------------------------------------------
def main():

    dram = DRAM()
    cache = Cache(dram)

    print(
        f"Simulating: {WAYS}-Way Set-Associative Cache, "
        f"{SETS} Sets, LRU Replacement\n"
    )

    requests = [

        # --- Phase 1: fill set 0 (4 compulsory misses) ---
        MemRequest(0, 0x00),
        MemRequest(0, 0x04),
        MemRequest(0, 0x08),
        MemRequest(0, 0x0C),

        # --- Phase 2: fill set 1 ---
        MemRequest(0, 0x01),
        MemRequest(0, 0x05),
        MemRequest(0, 0x09),
        MemRequest(0, 0x0D),

        # --- Phase 3: fill set 2 ---
        MemRequest(0, 0x02),
        MemRequest(0, 0x06),
        MemRequest(0, 0x0A),
        MemRequest(0, 0x0E),
        # Now sets 0, 1, 2 are full. Set 3 is still empty.

        # --- Phase 4: evictions ---
        MemRequest(0, 0x00),    # HIT: refreshes 0x00, so 0x04 becomes set 0's LRU
        MemRequest(0, 0x10),    # MISS in set 0 -> evicts 0x04 (NOT 0x00)
        MemRequest(0, 0x11),    # MISS in set 1 -> evicts 0x01 (oldest in set 1)
        MemRequest(0, 0x12),    # MISS in set 2 -> evicts 0x02 (oldest in set 2)
    ]

    for req in requests:
        cache.access(req)

    print(
        f"\nFinal Stats: {cache.hits} hits, {cache.misses} misses"
    )

    cache.dump()


if __name__ == "__main__":
    main()