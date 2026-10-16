.set noreorder
.set noat
.text
.balign 16

/* Integer arguments and floating arguments use separate EABI register banks.
 * The C worker is soft-float; its native callees may clobber f12-f15/FCSR.
 */
.macro save_inputs
    addiu $sp,$sp,-0x90
    sd $a0,0x00($sp)
    sd $a1,0x08($sp)
    sd $a2,0x10($sp)
    sd $a3,0x18($sp)
    sd $t0,0x20($sp)
    sd $t1,0x28($sp)
    sd $t2,0x30($sp)
    sd $t3,0x38($sp)
    sd $ra,0x40($sp)
    swc1 $f12,0x48($sp)
    swc1 $f13,0x4c($sp)
    swc1 $f14,0x50($sp)
    swc1 $f15,0x54($sp)
    cfc1 $v0,$31
    sw $v0,0x58($sp)
    sd $gp,0x60($sp)
.endm
.macro restore_inputs
    lw $v0,0x58($sp)
    ctc1 $v0,$31
    lwc1 $f12,0x48($sp)
    lwc1 $f13,0x4c($sp)
    lwc1 $f14,0x50($sp)
    lwc1 $f15,0x54($sp)
    ld $a0,0x00($sp)
    ld $a1,0x08($sp)
    ld $a2,0x10($sp)
    ld $a3,0x18($sp)
    ld $t0,0x20($sp)
    ld $t1,0x28($sp)
    ld $t2,0x30($sp)
    ld $t3,0x38($sp)
    ld $ra,0x40($sp)
    ld $gp,0x60($sp)
    addiu $sp,$sp,0x90
.endm

.globl zh_draw_hook
.ent zh_draw_hook
zh_draw_hook:
    save_inputs
    move $a0,$a2
    jal zh_ensure_draw
    move $a1,$a3
    restore_inputs
    /* Displaced original instructions at 002064F8/FC. */
    addiu $sp,$sp,-0x70
    sd $s0,0x10($sp)
    j 0x00206500
    nop
.end zh_draw_hook

.globl zh_text_hook
.ent zh_text_hook
zh_text_hook:
    save_inputs
    move $a1,$a3
    jal zh_prepare_text
    move $a2,$t0
    restore_inputs
    addiu $sp,$sp,-0x100
    lui $v0,0x48
    j 0x00207478
    nop
.end zh_text_hook

.globl zh_register_hook
.ent zh_register_hook
zh_register_hook:
    save_inputs
    jal zh_reset_fonts
    nop
    restore_inputs
    lui $v0,0x58
    move $t0,$a0
    j 0x00208238
    nop
.end zh_register_hook

.globl zh_open_hook
.ent zh_open_hook
zh_open_hook:
    save_inputs
    jal zh_before_open
    nop
    restore_inputs
    addiu $sp,$sp,-0x20
    lui $v0,0x58
    j 0x001a3a70
    nop
.end zh_open_hook

/* 00206E08: reuse the native CJK break candidate when either side of the
 * boundary is CJK. Pure Latin words retain the original English path.
 * At this site t0/t1 are dead; preserve v0=0x3002 from the delay slot.
 */
.macro cjk_boundary reg
    addiu $t0,\reg,-0x2e80
    sltiu $t0,$t0,0x7180     /* 2E80..9FFF: radicals, kana, punctuation, Han */
    bne $t0,$zero,zh_wrap_cjk
    nop
    ori $t0,$zero,0xf900
    subu $t0,\reg,$t0
    sltiu $t0,$t0,0x200      /* F900..FAFF: compatibility ideographs */
    bne $t0,$zero,zh_wrap_cjk
    nop
    ori $t0,$zero,0xff00
    subu $t0,\reg,$t0
    sltiu $t0,$t0,0xf0       /* FF00..FFEF: full/halfwidth forms */
    bne $t0,$zero,zh_wrap_cjk
    nop
.endm

.globl zh_wrap_boundary_hook
.ent zh_wrap_boundary_hook
zh_wrap_boundary_hook:
    bne $s7,$zero,zh_wrap_cjk
    nop
    cjk_boundary $s1
    lhu $t1,2($s2)
    cjk_boundary $t1
    j 0x002070d8             /* Original English space/hyphen handling. */
    nop
zh_wrap_cjk:
    j 0x00206f64             /* Original punctuation/alphanumeric checks. */
    nop
.end zh_wrap_boundary_hook

/* Three allocation call sites in 00449DF8 share this guard. On failure,
 * s6 is either zero or the temporary array; s7 is the native tree object.
 * Unwind to the existing epilogue only after freeing all owned arrays.
 */
.globl zh_tree_alloc_guard
.ent zh_tree_alloc_guard
zh_tree_alloc_guard:
    addiu $sp,$sp,-16
    sd $ra,0($sp)
    jal 0x00422f48
    nop
    ld $ra,0($sp)
    addiu $sp,$sp,16
    bne $v0,$zero,1f
    nop
    lui $v1,%hi(zh_diagnostics)
    addiu $v1,$v1,%lo(zh_diagnostics)
    lw $a0,60($v1)
    addiu $a0,$a0,1
    sw $a0,60($v1)
    beq $s6,$zero,2f
    nop
    jal 0x00422f28
    move $a0,$s6
2:
    jal 0x00449db0
    move $a0,$s7
    j 0x0044aa94
    nop
1:
    jr $ra
    nop
.end zh_tree_alloc_guard

/* The L1_Inter GUI paints its opaque title background AFTER normal subtitles.
 * Latch only the two L1 narrator DLLN name hashes when a caption is prepared.
 * Keep this latch past voice cleanup: the native caption may linger until its
 * minimum duration expires, after DAT_00480e78 has already been cleared.
 * Arguments a0/a1 and f12 belong to the original native preparation call.
 */
.globl zh_logo_subtitle_prepare
.ent zh_logo_subtitle_prepare
zh_logo_subtitle_prepare:
    beq $a0,$zero,1f
    move $v0,$zero
    lw $v0,4($a0)
    lui $v1,0x7160
    ori $v1,$v1,0x2625      /* L1_Intro_2=71602625, L1_Intro_3=71602626 */
    subu $v0,$v0,$v1
    sltiu $v0,$v0,2
1:
    lui $v1,%hi(zh_logo_subtitle_active)
    sw $v0,%lo(zh_logo_subtitle_active)($v1)
    j 0x00211b08
    nop
.end zh_logo_subtitle_prepare

/* Ordinary captions retain their original draw order. Logo captions defer the
 * entire native update/draw, so elapsed time advances only once per frame.
 */
.globl zh_subtitle_before_gui
.ent zh_subtitle_before_gui
zh_subtitle_before_gui:
    lui $v0,%hi(zh_logo_subtitle_active)
    lw $v0,%lo(zh_logo_subtitle_active)($v0)
    bne $v0,$zero,1f
    nop
    j 0x00211c30
    nop
1:
    jr $ra
    nop
.end zh_subtitle_before_gui

/* Both world+GUI and GUI-only frame paths use this call-site wrapper.
 * Flush/draw the original GUI first, then use the existing subtitle renderer,
 * style, timing and dynamic glyph cache. No text copies, allocations or I/O.
 */
.globl zh_logo_subtitle_after_gui
.ent zh_logo_subtitle_after_gui
zh_logo_subtitle_after_gui:
    addiu $sp,$sp,-16
    sd $ra,0($sp)
    jal 0x003c94c8
    nop
    ld $ra,0($sp)
    addiu $sp,$sp,16
    lui $v1,%hi(zh_logo_subtitle_active)
    lw $v0,%lo(zh_logo_subtitle_active)($v1)
    beq $v0,$zero,2f
    nop
    lui $v0,0x48
    lhu $v0,0xe80($v0)
    beq $v0,$zero,1f
    nop
    j 0x00211c30
    nop
1:
    sw $zero,%lo(zh_logo_subtitle_active)($v1)
2:
    jr $ra
    nop
.end zh_logo_subtitle_after_gui

.section .bss
.balign 4
.globl zh_logo_subtitle_active
zh_logo_subtitle_active:
    .space 4
.text
