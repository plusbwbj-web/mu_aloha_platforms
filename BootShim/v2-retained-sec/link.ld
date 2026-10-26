ENTRY(_start)
SECTIONS {
  . = 0;
  .text : { *(.text) }
  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
