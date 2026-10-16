/* Test-only adapter. Never linked into the PS2 patch. */
#include <stdint.h>
#include <stdlib.h>
typedef struct { uint32_t address; void *fn; } Entry;
static Entry entries[32];
static uint32_t used, counter, finish;
void host_bind(uint32_t address, void *fn) {
    uint32_t i;
    for (i=0;i<used;i++) if(entries[i].address==address) { entries[i].fn=fn; return; }
    if (used==32) abort();
    entries[used].address=address; entries[used++].fn=fn;
}
void *host_resolve(uint32_t address) {
    uint32_t i;
    for (i=0;i<used;i++) if(entries[i].address==address) return entries[i].fn;
    abort();
}
uint32_t host_ticks(void) { counter+=1000000; return counter; }
void host_finish_clear(void) { finish=0; }
uint32_t host_finish_status(void) { return finish; }
void host_set_finish(uint32_t value) { finish=value; }
