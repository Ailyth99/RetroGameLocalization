/* Fixed pixel cache for SLUS-217.46. Build freestanding, EABI32 / 64-bit GPRs.
 * Game layout/kerning remains native. Bounded compressed preload, no malloc/fd.
 */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef int i32;
typedef unsigned long long u64;
#ifndef HOST_TEST
typedef char require_pointer32[sizeof(void *) == 4 ? 1 : -1];
#endif

typedef struct { u32 u, v, advance; u16 code; short extra; } Glyph;
typedef struct { u32 first, count, tile_bytes, fallback; } FontConfig;
#include "bank_config.h"
#ifndef ZH_HARDWARE_FREEZE_GLYPHS
#define ZH_HARDWARE_FREEZE_GLYPHS 0
#endif
#ifndef ZH_HARDWARE_NATIVE_SYNC
#define ZH_HARDWARE_NATIVE_SYNC 0
#endif
#ifndef ZH_HARDWARE_SELECTIVE_TEXTURES
#define ZH_HARDWARE_SELECTIVE_TEXTURES 0
#endif
#ifndef ZH_HARDWARE_FRAME_SAFE
#define ZH_HARDWARE_FRAME_SAFE 0
#endif

/* Diagnostic build only: freeze atlas contents after a level-open trigger.
 * magic, version, enabled, in-level, suppressed batches, last profile trigger.
 * Font registration must NOT clear this state during level loading. MainMenu
 * restores normal cache loading. No overlay, allocations or diagnostic I/O.
 */
volatile u32 zh_hardware_diagnostic[6] = {
    0x4857465a, 1, ZH_HARDWARE_FREEZE_GLYPHS, 0, 0, 0
};
/* Optional hardware experiment: retain native submission/DMA waits, but do
 * not append or acknowledge a private GS FINISH. Full glyph loading stays on.
 * magic, version, enabled, native-sync batches. No additional pixel buffers.
 */
volatile u32 zh_hardware_sync[4] = {
    0x5357465a, 1, ZH_HARDWARE_NATIVE_SYNC, 0
};
/* Optional hardware experiment: invalidate only modified font textures in the
 * native four-slot residency table. Keep normal DMA/GS fencing and full text.
 * magic, version, enabled, dirty batches, invalidated residency slots.
 */
volatile u32 zh_hardware_texture[5] = {
    0x5457465a, 1, ZH_HARDWARE_SELECTIVE_TEXTURES, 0, 0
};
/* Hoist the native display preparation before an extra mid-frame submission.
 * magic, version, enabled, prepared this frame, early preparations,
 * consumed preparations at native frame end, original software buffer index.
 */
volatile u32 zh_hardware_frame[7] = {
    0x4257465a, 1, ZH_HARDWARE_FRAME_SAFE, 0, 0, 0, 0
};

typedef struct {
    u32 magic, version, size, calls, hits, loads, evictions, fences;
    u32 opens, blocks, read_bytes, errors, last_error, last_key, font_resets, tree_failures;
    u32 max_request, direct_misses, io_timeouts, finish_timeouts, bytes_reserved;
    u32 resident_hits, io_ticks, fence_ticks, decode_ticks, write_ticks;
    u32 miss_batches, max_batch_ticks, last_batch_ticks, batch_ticks, reserved[2];
} Diagnostics;
volatile Diagnostics zh_diagnostics = {0x4643485a, 2, sizeof(Diagnostics)};
typedef struct { u32 key, stamp; } Slot;
typedef struct { u32 font, page, image, texture; } Binding;
static Slot slots[288];
/* Direct glyph -> atlas slot lookup; zero means absent. */
static u16 glyph_slots[sizeof(bank_offsets) / sizeof(bank_offsets[0])];
static u8 request_bits[(sizeof(bank_offsets) / sizeof(bank_offsets[0]) + 7) / 8];
static Binding bindings[3];
static u32 requests[288], request_count, clock_stamp, validated;
static u8 decoded[512];
static i32 handle = -1;
static u32 block_offset, block_length;
static const u8 *block_data;
static u32 resident_ready = 1, active_profile, loading_profile;
/* Separate load-screen I/O from in-frame glyph misses in the existing counters.
 * magic, version, loads, errors, bytes, ticks, current profile, last error. */
volatile u32 zh_profile_diagnostics[8] = {0x5052485a, 1};

#ifdef HOST_TEST
extern void *host_resolve(u32 address);
extern u32 host_ticks(void);
extern void host_finish_clear(void);
extern u32 host_finish_status(void);
#define FN(addr, ret, ...) ((ret (*)(__VA_ARGS__))host_resolve(addr))
#define TICKS() host_ticks()
#else
#define FN(addr, ret, ...) ((ret (*)(__VA_ARGS__))(addr))
static u32 ticks(void) { u32 t; __asm__ volatile("mfc0 %0,$9" : "=r"(t)); return t; }
#define TICKS() ticks()
#endif
#define WORD(addr) (*(volatile u32 *)(addr))
#define BYTE(addr) (*(volatile u8 *)(addr))

static void error(u32 reason, u32 key) {
    zh_diagnostics.errors++;
    zh_diagnostics.last_error = reason;
    zh_diagnostics.last_key = key;
}

/* Exact float bits for (2*x+1)/(2*dimension), without soft-float helpers. */
static u32 coordinate(u32 numerator, u32 dimension_log2) {
    u32 n = numerator, exponent = 0;
    while (n >>= 1) exponent++;
    return ((exponent + 126 - dimension_log2) << 23) |
           ((numerator ^ (1u << exponent)) << (23 - exponent));
}

static void uv(Glyph *glyph, u32 slot) {
    u32 x, y, log2;
    if (slot < 240) {
        x = (slot % 16) * 32 + 1; y = (slot / 16) * 34 + 1; log2 = 9;
    } else {
        slot -= 240;
        x = (slot % 8) * 16 + 1; y = (slot / 8) * 18 + 1; log2 = 7;
    }
    glyph->u = coordinate(x * 2 + 1, log2);
    glyph->v = coordinate(y * 2 + 1, log2);
}

void zh_reset_fonts(void) {
    u32 i;
    for (i = 0; i < 288; i++) slots[i].key = slots[i].stamp = 0;
    for (i = 0; i < sizeof(glyph_slots) / sizeof(glyph_slots[0]); i++) glyph_slots[i] = 0;
    for (i = 0; i < sizeof(request_bits); i++) request_bits[i] = 0;
    request_count = 0;
    for (i = 0; i < 3; i++) bindings[i].font = bindings[i].page = bindings[i].image = 0;
    clock_stamp = 0;
    zh_diagnostics.font_resets++;
}

static int same(const char *a, const char *b) {
    while (*a && *a == *b) { a++; b++; }
    return *a == *b;
}

static i32 identify(u32 font, u32 page) {
    i32 id;
    u32 texture, object, picture, image;
    const char *name, *cursor;
    if (!font || !page || WORD(font + 8) != 1 || WORD(font + 4) != page) return -1;
    /* Registration invalidates bindings. Check the backing image as well so a
     * recycled texture object cannot silently retain another atlas' slots. */
    for (id = 0; id < 3; id++) if (bindings[id].font == font && bindings[id].page == page) {
        texture = WORD(page + 100);
        if (texture == bindings[id].texture && texture < 250 &&
            (object = WORD(0x004e8c60 + texture * 4)) && (picture = WORD(object + 4)) &&
            ((picture + *(u16 *)(picture + 12)) & 0x0fffffffu) == bindings[id].image) return id;
        break;
    }
    /* The native FONT loader prepends its resource namespace (\\fonts\\). */
    name = (const char *)(font + 12);
    for (cursor = name; *cursor; cursor++)
        if (*cursor == '\\' || *cursor == '/') name = cursor + 1;
    if (same(name, "Times New Roman_20_Bold")) id = 0;
    else if (same(name, "Verdana_10")) id = 1;
    else if (same(name, "Verdana_20")) id = 2;
    else return -1;
    if (WORD(page + 120) != font_config[id].count ||
        WORD(page + 112) != (id == 1 ? 128u : 512u) ||
        WORD(page + 116) != (id == 1 ? 128u : 512u)) { error(3, id); return -1; }
    texture = WORD(page + 100);
    if (texture >= 250 || !(object = WORD(0x004e8c60 + texture * 4))) { error(4,id); return -1; }
    picture = WORD(object + 4);
    if (!picture || BYTE(picture + 19) != 4 ||
        WORD(picture + 8) != (id == 1 ? 8192u : 131072u) ||
        *(u16 *)(picture + 20) != (id == 1 ? 128u : 512u) ||
        *(u16 *)(picture + 22) != (id == 1 ? 128u : 512u)) { error(5,id); return -1; }
    image = (picture + *(u16 *)(picture + 12)) & 0x0fffffff;
    if (bindings[id].font && (bindings[id].font != font || bindings[id].page != page ||
                             bindings[id].image != image)) zh_reset_fonts();
    bindings[id].font = font; bindings[id].page = page;
    bindings[id].texture = texture; bindings[id].image = image;
    return id;
}

static u32 current_font(void) {
    u32 slot = WORD(0x00480da8);
    return slot < 4 ? WORD(0x005841e0 + slot * 4) : 0;
}

static u32 key_for(i32 id, Glyph *glyph) {
    u32 base = WORD(bindings[id].page + 104), address = (u32)glyph;
    if (address < base || ((address - base) & 15) ||
        (address - base) / 16 >= font_config[id].count) return 0;
    return ((id + 1u) << 16) | ((address - base) / 16 + 1);
}

static Glyph *record(u32 key) {
    return (Glyph *)(WORD(bindings[(key >> 16) - 1].page + 104) + ((key & 65535) - 1) * 16);
}

static u32 glyph_index(u32 key) {
    return font_config[(key >> 16) - 1].first + (key & 65535) - 1;
}

static i32 find_slot(u32 key) {
    u32 id = (key >> 16) - 1;
    if ((key & 65535) - 1 == font_config[id].fallback) return id == 0 ? 0 : id == 2 ? 1 : 240;
    if (record(key)->code == 32) return id == 1 ? 241 : 2;
    return (i32)glyph_slots[glyph_index(key)] - 1;
}

static int requested(u32 key) {
    u32 i = glyph_index(key);
    return request_bits[i >> 3] & (1u << (i & 7));
}

static void clear_requests(void) {
    u32 i, index;
    for (i = 0; i < request_count; i++) {
        index = glyph_index(requests[i]);
        request_bits[index >> 3] &= ~(1u << (index & 7));
    }
    request_count = 0;
}

static void add_request(u32 key) {
    u32 i = glyph_index(key);
    request_bits[i >> 3] |= 1u << (i & 7);
    requests[request_count++] = key;
}

static i32 victim(u32 key) {
    u32 i = (key >> 16) == 2 ? 242 : 3, end = i == 242 ? 288 : 240;
    u32 oldest = 0xffffffff;
    i32 selected = -1;
    for (; i < end; i++) {
        if (!slots[i].key) return i;
        if (!requested(slots[i].key) && slots[i].stamp < oldest) {
            oldest = slots[i].stamp; selected = i;
        }
    }
    return selected; /* Caller leaves the rest for synchronous draw-time misses. */
}

static void prepare_scanout(void) {
    u32 original;
    if (!zh_hardware_frame[2] || zh_hardware_frame[3]) return;
    /* Match the native flip guard. The special 16-bit colour / 32-bit depth
     * path does not alternate displays and already draws to the other buffer.
     */
    if (!BYTE(0x004d8f34) || (BYTE(0x004d8f33) &&
        *(volatile u16 *)0x00481954 == 16 && *(volatile u16 *)0x00481956 == 32)) return;
    original = WORD(0x00481950);
    if (original > 1) return;
    /* Previous DMA has completed. Apply the same wait and frame blend that
     * 00259618 normally runs before displaying that completed frame.
     */
    if (BYTE(0x004d8f38)) FN(0x00424fd8, u32, void)();
    FN(0x002596f0, void, u32)(0);
    WORD(0x00481950) = original ^ 1u;
    FN(0x00258ca0, void, void)();
    /* Keep all remaining command construction on its ORIGINAL target.
     * Native frame-end still commits the software flip, once, as before.
     */
    WORD(0x00481950) = original;
    zh_hardware_frame[6] = original;
    zh_hardware_frame[3] = 1;
    zh_hardware_frame[4]++;
}

u32 zh_frame_vsync_guard(void) {
    if (zh_hardware_frame[2] && zh_hardware_frame[3]) return 0;
    return FN(0x00424fd8, u32, void)();
}

void zh_frame_blend_guard(u32 mode) {
    if (zh_hardware_frame[2] && zh_hardware_frame[3] && !mode) {
        zh_hardware_frame[3] = 0;
        zh_hardware_frame[5]++;
        return;
    }
    FN(0x002596f0, void, u32)(mode);
}

/* Native batch flush + previous DMA wait + current chain submission + DMA wait.
 * FLUSHA/TEXFLUSH/FINISH also order outstanding GS work before atlas reuse.
 */
static int fence(void) {
    u32 *p, start;
    if (!BYTE(0x004d8f28)) { error(6,0); return 0; }
    FN(0x00251c40, void, void)();
    FN(0x00258138, void, void)();
    prepare_scanout();
    if (zh_hardware_sync[2]) {
        /* Drain old main-memory texture sources before atlas writes. Texture
         * upload/sampling ordering uses the game's native command path; this
         * candidate still requires a real PS2 test of GS/display behaviour.
         */
        FN(0x00257ef0, void, u32)(0);
        FN(0x00258138, void, void)();
        zh_hardware_sync[3]++;
        zh_diagnostics.fences++;
        return 1;
    }
#ifdef HOST_TEST
    host_finish_clear();
#else
    *(volatile u64 *)0x12001000 = 2;
#endif
    p = FN(0x00257ca8, u32 *, u32)(4);
    if (!p) { error(7,0); return 0; }
    p[0]=0x10000003; p[1]=0; p[2]=0x13000000; p[3]=0x50000003;
    p[4]=0x8002; p[5]=0x10000000; p[6]=14; p[7]=0;
    p[8]=0; p[9]=0; p[10]=0x3f; p[11]=0;
    p[12]=0; p[13]=0; p[14]=0x61; p[15]=0;
    FN(0x00257ef0, void, u32)(0);
    FN(0x00258138, void, void)();
    start = TICKS();
#ifdef HOST_TEST
    while (!(host_finish_status() & 2)) {
#else
    while (!(*(volatile u64 *)0x12001000 & 2)) {
#endif
        if ((u32)(TICKS() - start) > 150000000u) {
            zh_diagnostics.finish_timeouts++; error(8,0); return 0;
        }
    }
    zh_diagnostics.fences++;
    return 1;
}

static int read_block(u32 offset) {
    i32 got;
    u32 start, base = (offset / 0xc000) * 0xc000;
    if (block_data && base == block_offset) return 1;
    FN(0x0026a188, void, i32, u32)(handle, base);
    start = TICKS();
    do {
        got = FN(0x00269d18, i32, i32, const u8 **, u32)(handle, &block_data, 0);
        if (got < 0) { error(10,offset); return 0; }
        if ((u32)(TICKS() - start) > 150000000u) {
            zh_diagnostics.io_timeouts++; error(11,offset); return 0;
        }
    } while (!got);
    block_offset = base; block_length = got;
    zh_diagnostics.blocks++; zh_diagnostics.read_bytes += got;
    return 1;
}

static int open_bank(void) {
    u32 i;
    block_data = 0;
    handle = FN(0x001a3a68, i32, const char *)("Fonts\\ZHGLYPH.BIN");
    if (handle < 0 || handle > 1) { error(9,0); handle = -1; return 0; }
    zh_diagnostics.opens++;
    if (validated) return 1;
    if (!read_block(0) || block_length < 32) return 0;
    for (i = 0; i < 32; i++) if (block_data[i] != bank_identity[i]) { error(12,i); return 0; }
    validated = 1;
    return 1;
}

static void close_bank(void) {
    if (handle >= 0) FN(0x001a3ef8, void, i32)(handle);
    handle = -1; block_data = 0;
}

static u32 little32(const u8 *p) {
    return p[0] | (p[1] << 8) | (p[2] << 16) | (p[3] << 24);
}

static u32 lowercase(u32 c) { return c >= 'A' && c <= 'Z' ? c + 32 : c; }

static int profile_match(const char *name, const char *trigger, u32 id) {
    while (*trigger && lowercase((u8)*name) == lowercase((u8)*trigger)) { name++; trigger++; }
    if (*trigger) return 0;
    if (!id) return !*name;
    return (name[0] == '.' && lowercase((u8)name[1]) == 'p' && lowercase((u8)name[2]) == 's' && name[3] == '2' && !name[4]) ||
           (name[0] == '.' && lowercase((u8)name[1]) == 'a' && lowercase((u8)name[2]) == 'm' && !name[3]);
}

/* Runs BEFORE the native open reserves a handle. One sequential preload during
 * the resource transition; no allocations, no permanently retained handle. */
void zh_before_open(const char *path) {
    const char *name = path, *p;
    const u8 *data = 0;
    i32 fd = -1, got;
    u32 id, i, start, wait_start, position = 0, payload = 0, data_size = 0;
    u32 expected_hash = 0, hash = 2166136261u, reason = 0;
    if (!path || loading_profile || handle >= 0) return;
    for (p = path; *p; p++) if (*p == '/' || *p == '\\') name = p + 1;
    for (id = 0; id < sizeof(resident_profiles) / sizeof(resident_profiles[0]); id++)
        if (profile_match(name, resident_profiles[id].trigger, id)) break;
    if (id == sizeof(resident_profiles) / sizeof(resident_profiles[0])) return;
    /* Gate on the requested level, even when USB profile loading fails or
     * the matching profile was already loaded. This keeps the test meaningful
     * without assuming that the on-hardware preload succeeded. */
    zh_hardware_diagnostic[3] = id != 0;
    zh_hardware_diagnostic[5] = id;
    if (resident_ready && id == active_profile) return;
    loading_profile = 1;
    start = TICKS();
    fd = FN(0x001a3a68, i32, const char *)(resident_profiles[id].path);
    if (fd < 0 || fd > 1) { reason = 1; goto done; }
    wait_start = TICKS();
    for (;;) {
        got = FN(0x00269d18, i32, i32, const u8 **, u32)(fd, &data, 0);
        if (got < 0) { reason = 2; goto done; }
        if (!got) {
            if ((u32)(TICKS() - wait_start) > 150000000u) { reason = 3; goto done; }
            continue;
        }
        wait_start = TICKS();
        zh_profile_diagnostics[4] += got;
        if (!position) {
            if (got < 64) { reason = 4; goto done; }
            for (i = 0; i < 32; i++) if (data[i] != bank_identity[i]) { reason = 4; goto done; }
            payload = little32(data + 56); data_size = little32(data + 52);
            expected_hash = little32(data + 60);
            if (little32(data + 32) != 0x5250485a || little32(data + 36) != PROFILE_VERSION ||
                little32(data + 40) != id || little32(data + 44) != sizeof(bank_offsets) / 4 ||
                little32(data + 48) != PROFILE_INDEX_BYTES || data_size > sizeof(resident_data) ||
                payload != PROFILE_INDEX_BYTES + data_size) { reason = 4; goto done; }
            /* After this point a short read must disable the partly replaced
             * preload. The immutable disk offsets remain a valid fallback. */
            resident_ready = 0;
        }
        for (i = !position ? 64 : 0; i < (u32)got && position + i < 64 + payload; i++) {
            u32 offset = position + i - 64;
            hash = (hash ^ data[i]) * 16777619u;
            if (offset < sizeof(resident_index)) ((u8 *)resident_index)[offset] = data[i];
            else if (offset >= PROFILE_INDEX_BYTES) resident_data[offset - PROFILE_INDEX_BYTES] = data[i];
        }
        position += got;
        if (position >= 64 + payload) break;
    }
    if (hash != expected_hash) { reason = 5; goto done; }
    for (i = 0; i < sizeof(resident_index) / 2; i++) if (resident_index[i]) {
        u32 offset = ((u32)resident_index[i] - 1) * RESIDENT_OFFSET_UNIT, length;
        if (offset + 4 > data_size) { reason = 6; goto done; }
        length = resident_data[offset + 2] | (resident_data[offset + 3] << 8);
        if (offset + 4 + length > data_size) { reason = 6; goto done; }
    }
    active_profile = id; resident_ready = 1;
    zh_profile_diagnostics[2]++;
    zh_profile_diagnostics[6] = id;
done:
    if (fd >= 0 && fd <= 1) FN(0x001a3ef8, void, i32)(fd);
    if (reason) { zh_profile_diagnostics[3]++; zh_profile_diagnostics[7] = reason; }
    zh_profile_diagnostics[5] += (u32)(TICKS() - start);
    loading_profile = 0;
}

/* Raw LZ4 block decoder with bounds checks, no allocation, maximum output 512. */
int zh_decode(const u8 *src, u32 length, u8 *out, u32 capacity, u32 mode) {
    u32 ip = 0, op = 0, n, offset, token, more, i;
    if (!mode) {
        if (length != capacity) return 0;
        for (i = 0; i < capacity; i++) out[i] = src[i];
        return 1;
    }
    if (mode != 1) return 0;
    while (ip < length) {
        token = src[ip++]; n = token >> 4;
        if (n == 15) do {
            if (ip >= length) return 0;
            more = src[ip++]; n += more;
        } while (more == 255);
        if (n > length - ip || n > capacity - op) return 0;
        for (i = 0; i < n; i++) out[op++] = src[ip++];
        if (ip == length) return op == capacity;
        if (length - ip < 2) return 0;
        offset = src[ip] | (src[ip + 1] << 8); ip += 2;
        if (!offset || offset > op) return 0;
        n = (token & 15) + 4;
        if ((token & 15) == 15) do {
            if (ip >= length) return 0;
            more = src[ip++]; n += more;
        } while (more == 255);
        if (n > capacity - op) return 0;
        for (i = 0; i < n; i++) { out[op] = out[op - offset]; op++; }
    }
    return op == capacity;
}

static int tile(u32 key) {
    u32 id = (key >> 16) - 1, index = (key & 65535) - 1;
    u32 offset = bank_offsets[font_config[id].first + index], local, mode, length, start;
    const u8 *p;
    u32 available;
    if (resident_ready && resident_index[font_config[id].first + index]) {
        local = ((u32)resident_index[font_config[id].first + index] - 1) * RESIDENT_OFFSET_UNIT;
        if (local + 4 > sizeof(resident_data)) { error(13,key); return 0; }
        p = resident_data + local;
        available = sizeof(resident_data) - local;
        zh_diagnostics.resident_hits++;
    } else {
        int ok;
        start = TICKS();
        ok = (handle >= 0 || open_bank()) && read_block(offset);
        zh_diagnostics.io_ticks += (u32)(TICKS() - start);
        if (!ok) return 0;
        local = offset - block_offset;
        if (local + 4 > block_length) { error(13,key); return 0; }
        p = block_data + local;
        available = block_length - local;
    }
    mode = p[0] | (p[1] << 8); length = p[2] | (p[3] << 8);
    start = TICKS();
    if (4 + length > available ||
        !zh_decode(p + 4, length, decoded, font_config[id].tile_bytes, mode)) {
        error(14,key); return 0;
    }
    zh_diagnostics.decode_ticks += (u32)(TICKS() - start);
    return 1;
}

static int draw_tile(u32 key, u32 slot) {
    u32 id = (key >> 16) - 1, small = id == 1;
    u32 local_slot = small ? slot - 240 : slot, columns = small ? 8 : 16;
    u32 cw = small ? 16 : 32, ch = small ? 18 : 34, dim = small ? 128 : 512;
    u32 x = local_slot % columns * cw, y = local_slot / columns * ch, xx, yy;
    u32 sample = small ? 16 : id == 0 ? 31 : 32, advance, bits;
    Glyph *glyph = record(key);
    u8 *image = (u8 *)bindings[id].image;
    /* Advance was validated as a positive integer by the builder. */
    bits = glyph->advance;
    if ((bits >> 23) < 127 || (bits >> 23) > 131) { error(15,key); return 0; }
    advance = (0x800000 | (bits & 0x7fffff)) >> (150 - (bits >> 23));
    if (advance + 2 > cw || x + cw > dim || y + ch > dim) { error(15,key); return 0; }
    /* Cells start on a byte boundary. Clear two 4bpp pixels at once, then
     * shift each decoded row one nibble to retain the one-pixel left gutter.
     * Odd/even advances preserve both outside nibbles and the native CLUT. */
    for (yy = 0; yy < ch; yy++) {
        u8 *row = image + ((y + yy) * dim + x) / 2;
        for (xx = 0; xx < cw / 2; xx++) row[xx] = small ? 255 : 0;
    }
    for (yy = 0; yy < sample; yy++) {
        u8 *row = image + ((y + 1 + yy) * dim + x) / 2;
        const u8 *src = decoded + yy * (cw / 2);
        row[0] = (small ? 15 : 0) | (src[0] << 4);
        for (xx = 1; xx < (advance + 1) / 2; xx++)
            row[xx] = (src[xx - 1] >> 4) | (src[xx] << 4);
        if (!(advance & 1)) row[advance / 2] = (src[advance / 2 - 1] >> 4) | (small ? 240 : 0);
    }
    if (slots[slot].key) {
        glyph_slots[glyph_index(slots[slot].key)] = 0;
        zh_diagnostics.evictions++;
    }
    slots[slot].key = key; slots[slot].stamp = ++clock_stamp;
    glyph_slots[glyph_index(key)] = slot + 1;
    uv(glyph, slot);
    zh_diagnostics.loads++;
    return 1;
}

static void load_requests(void) {
    u32 i, dirty = 0, has_missing = 0, start, batch_start, elapsed;
    i32 slot;
    if (zh_hardware_diagnostic[2] && zh_hardware_diagnostic[3]) {
        zh_hardware_diagnostic[4]++;
        return;
    }
    for (i = 0; i < request_count; i++) if (find_slot(requests[i]) < 0) has_missing = 1;
    if (!has_missing) return;
    batch_start = start = TICKS();
    zh_diagnostics.miss_batches++;
    i = fence();
    zh_diagnostics.fence_ticks += (u32)(TICKS() - start);
    if (!i) return;
    for (i = 0; i < request_count; i++) {
        u32 key = requests[i], id = (key >> 16) - 1;
        if (find_slot(key) >= 0) continue;
        slot = victim(key);
        if (slot < 0) continue;
        if (!tile(key)) break;
        start = TICKS();
        if (draw_tile(key, slot)) dirty |= 1u << id;
        zh_diagnostics.write_ticks += (u32)(TICKS() - start);
    }
    if (handle >= 0) {
        start = TICKS();
        close_bank();
        zh_diagnostics.io_ticks += (u32)(TICKS() - start);
    }
    for (i = 0; i < 3; i++) if (dirty & (1u << i)) {
        u32 p = bindings[i].image;
        FN(0x00436fa0, void, u32, u32)(p, p + (i == 1 ? 8192 : 131072) - 1);
    }
    if (dirty) {
        if (zh_hardware_texture[2]) {
            u32 entry, id;
            zh_hardware_texture[3]++;
            /* Invalidate EVERY resident copy of the changed texture, including
             * the shared large atlas. Leave other textures' residency intact.
             * A texture absent from this table already needs a native upload.
             */
            for (entry = 0; entry < 4; entry++) {
                u32 texture = WORD(0x00481918 + entry * 4);
                for (id = 0; id < 3; id++) if ((dirty & (1u << id)) &&
                                               texture == bindings[id].texture) {
                    FN(0x00254a50, void, u32)(entry);
                    zh_hardware_texture[4]++;
                    break;
                }
            }
        } else FN(0x00254a70, void, void)();
    }
    elapsed = (u32)(TICKS() - batch_start);
    zh_diagnostics.last_batch_ticks = elapsed;
    zh_diagnostics.batch_ticks += elapsed;
    if (elapsed > zh_diagnostics.max_batch_ticks) zh_diagnostics.max_batch_ticks = elapsed;
}

void zh_prepare_text(const u16 *text, u32 flags, i32 limit) {
    u32 font = current_font(), page, index, key, i, j, count, missing = 0;
    i32 id;
    Glyph *glyph;
    if (!text || !font || (flags & 0x400)) return;
    id = identify(font, WORD(font + 4));
    if (id < 0) return;
    clear_requests();
    count = limit < 0 || limit > 4095 ? 4096 : limit + 1;
    for (index = 0; index < count && text[index]; index++) {
        if (text[index] == 32 || text[index] == 10 || text[index] == 13) continue;
        page = 0;
        glyph = FN(0x00208568, Glyph *, u32, u32, u32, u32 *)(font, text[index], flags, &page);
        if (!glyph || page != bindings[id].page) continue;
        key = key_for(id, glyph);
        if (!key || requested(key)) continue;
        if (request_count == 288) break; /* Remaining glyphs use the draw-time path. */
        add_request(key);
        if (find_slot(key) < 0) missing = 1;
    }
    if (request_count > zh_diagnostics.max_request) zh_diagnostics.max_request = request_count;
    if (!missing) return;
    /* Bank order: group disk reads, independent of text order. */
    for (i = 1; i < request_count; i++) {
        key = requests[i]; j = i;
        while (j && requests[j - 1] > key) { requests[j] = requests[j - 1]; j--; }
        requests[j] = key;
    }
    load_requests();
}

void zh_ensure_draw(Glyph *glyph, u32 page) {
    u32 key;
    i32 id, slot;
    zh_diagnostics.calls++;
    if (!glyph || !page || (id = identify(current_font(), page)) < 0) return;
    key = key_for(id, glyph);
    if (!key) return;
    slot = find_slot(key);
    if (slot < 0) {
        zh_diagnostics.direct_misses++;
        clear_requests(); add_request(key);
        load_requests();
        slot = find_slot(key);
    } else zh_diagnostics.hits++;
    if (slot < 0) { uv(glyph, id == 0 ? 0 : id == 2 ? 1 : 240); return; }
    slots[slot].stamp = ++clock_stamp;
    /* Dynamic UVs were written once when the tile was installed. */
    if (slot < 3 || slot == 240 || slot == 241) uv(glyph, slot);
}
