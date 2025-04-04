#ifndef ATOMIC_UTILS_H
#define ATOMIC_UTILS_H

#include "pico/critical_section.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Global critical section for all atomic operations.
// Define this variable in one C source file (e.g. main.c):
//    critical_section_t atomic_global_cs;
extern critical_section_t atomic_global_cs;

// Initialize the global critical section. Call once during system init.
static inline void atomic_init(void) {
    critical_section_init(&atomic_global_cs);
}

/*----------------------------------------------------------------------------
  Macro to generate basic atomic operations (get, set, increment, decrement,
  add, subtract) for a given type.
----------------------------------------------------------------------------*/
#define DEFINE_ATOMIC_OPS(type, suffix)                                  \
static inline type atomic_get_##suffix(volatile type *ptr) {               \
    type val;                                                            \
    critical_section_enter_blocking(&atomic_global_cs);                  \
    val = *ptr;                                                          \
    critical_section_exit(&atomic_global_cs);                            \
    return val;                                                          \
}                                                                        \
static inline void atomic_set_##suffix(volatile type *ptr, type value) {    \
    critical_section_enter_blocking(&atomic_global_cs);                  \
    *ptr = value;                                                        \
    critical_section_exit(&atomic_global_cs);                            \
}                                                                        \
static inline type atomic_increment_##suffix(volatile type *ptr) {         \
    type ret;                                                            \
    critical_section_enter_blocking(&atomic_global_cs);                  \
    ret = ++(*ptr);                                                      \
    critical_section_exit(&atomic_global_cs);                            \
    return ret;                                                          \
}                                                                        \
static inline type atomic_decrement_##suffix(volatile type *ptr) {         \
    type ret;                                                            \
    critical_section_enter_blocking(&atomic_global_cs);                  \
    ret = --(*ptr);                                                      \
    critical_section_exit(&atomic_global_cs);                            \
    return ret;                                                          \
}                                                                        \
static inline void atomic_add_##suffix(volatile type *ptr, type addend) {    \
    critical_section_enter_blocking(&atomic_global_cs);                  \
    *ptr += addend;                                                      \
    critical_section_exit(&atomic_global_cs);                            \
}                                                                        \
static inline void atomic_subtract_##suffix(volatile type *ptr, type subtrahend) { \
    critical_section_enter_blocking(&atomic_global_cs);                  \
    *ptr -= subtrahend;                                                  \
    critical_section_exit(&atomic_global_cs);                            \
}

/*----------------------------------------------------------------------------
  Macro to generate atomic bit operations (set, clear, toggle) for a given type.
  These operations treat the variable as a bitfield.
----------------------------------------------------------------------------*/
#define DEFINE_ATOMIC_BIT_OPS(type, suffix)                              \
static inline void atomic_set_bit_##suffix(volatile type *ptr, uint8_t bit) { \
    critical_section_enter_blocking(&atomic_global_cs);                  \
    *ptr |= ((type)1 << bit);                                            \
    critical_section_exit(&atomic_global_cs);                            \
}                                                                        \
static inline void atomic_clear_bit_##suffix(volatile type *ptr, uint8_t bit) { \
    critical_section_enter_blocking(&atomic_global_cs);                  \
    *ptr &= ~((type)1 << bit);                                           \
    critical_section_exit(&atomic_global_cs);                            \
}                                                                        \
static inline void atomic_toggle_bit_##suffix(volatile type *ptr, uint8_t bit) { \
    critical_section_enter_blocking(&atomic_global_cs);                  \
    *ptr ^= ((type)1 << bit);                                            \
    critical_section_exit(&atomic_global_cs);                            \
}

/*----------------------------------------------------------------------------
  Generate functions for desired types.
----------------------------------------------------------------------------*/
DEFINE_ATOMIC_OPS(uint8_t, uint8)
DEFINE_ATOMIC_OPS(uint16_t, uint16)
DEFINE_ATOMIC_OPS(uint32_t, uint32)
DEFINE_ATOMIC_OPS(int, int)

DEFINE_ATOMIC_BIT_OPS(uint8_t, uint8)
DEFINE_ATOMIC_BIT_OPS(uint16_t, uint16)
DEFINE_ATOMIC_BIT_OPS(uint32_t, uint32)
DEFINE_ATOMIC_BIT_OPS(int, int)  // For signed int bit operations, if needed

/*----------------------------------------------------------------------------
  Generic macros using _Generic to select the correct function based on type.
----------------------------------------------------------------------------*/
#define atomic_get(ptr) _Generic((ptr),                           \
    volatile uint8_t*: atomic_get_uint8,                             \
    uint8_t*: atomic_get_uint8,                                      \
    volatile uint16_t*: atomic_get_uint16,                           \
    uint16_t*: atomic_get_uint16,                                    \
    volatile uint32_t*: atomic_get_uint32,                           \
    uint32_t*: atomic_get_uint32,                                    \
    volatile int*: atomic_get_int,                                   \
    int*: atomic_get_int                                             \
)(ptr)

#define atomic_set(ptr, value) _Generic((ptr),                     \
    volatile uint8_t*: atomic_set_uint8,                             \
    uint8_t*: atomic_set_uint8,                                      \
    volatile uint16_t*: atomic_set_uint16,                           \
    uint16_t*: atomic_set_uint16,                                    \
    volatile uint32_t*: atomic_set_uint32,                           \
    uint32_t*: atomic_set_uint32,                                    \
    volatile int*: atomic_set_int,                                   \
    int*: atomic_set_int                                             \
)(ptr, value)

#define atomic_increment(ptr) _Generic((ptr),                      \
    volatile uint8_t*: atomic_increment_uint8,                       \
    uint8_t*: atomic_increment_uint8,                                \
    volatile uint16_t*: atomic_increment_uint16,                     \
    uint16_t*: atomic_increment_uint16,                              \
    volatile uint32_t*: atomic_increment_uint32,                     \
    uint32_t*: atomic_increment_uint32,                              \
    volatile int*: atomic_increment_int,                             \
    int*: atomic_increment_int                                       \
)(ptr)

#define atomic_decrement(ptr) _Generic((ptr),                      \
    volatile uint8_t*: atomic_decrement_uint8,                       \
    uint8_t*: atomic_decrement_uint8,                                \
    volatile uint16_t*: atomic_decrement_uint16,                     \
    uint16_t*: atomic_decrement_uint16,                              \
    volatile uint32_t*: atomic_decrement_uint32,                     \
    uint32_t*: atomic_decrement_uint32,                              \
    volatile int*: atomic_decrement_int,                             \
    int*: atomic_decrement_int                                       \
)(ptr)

#define atomic_set_bit(ptr, bit) _Generic((ptr),                    \
    volatile uint8_t*: atomic_set_bit_uint8,                         \
    uint8_t*: atomic_set_bit_uint8,                                  \
    volatile uint16_t*: atomic_set_bit_uint16,                       \
    uint16_t*: atomic_set_bit_uint16,                                \
    volatile uint32_t*: atomic_set_bit_uint32,                       \
    uint32_t*: atomic_set_bit_uint32,                                \
    volatile int*: atomic_set_bit_int,                               \
    int*: atomic_set_bit_int                                         \
)(ptr, bit)

#define atomic_clear_bit(ptr, bit) _Generic((ptr),                  \
    volatile uint8_t*: atomic_clear_bit_uint8,                       \
    uint8_t*: atomic_clear_bit_uint8,                                \
    volatile uint16_t*: atomic_clear_bit_uint16,                     \
    uint16_t*: atomic_clear_bit_uint16,                              \
    volatile uint32_t*: atomic_clear_bit_uint32,                     \
    uint32_t*: atomic_clear_bit_uint32,                              \
    volatile int*: atomic_clear_bit_int,                             \
    int*: atomic_clear_bit_int                                       \
)(ptr, bit)

#define atomic_toggle_bit(ptr, bit) _Generic((ptr),                 \
    volatile uint8_t*: atomic_toggle_bit_uint8,                      \
    uint8_t*: atomic_toggle_bit_uint8,                               \
    volatile uint16_t*: atomic_toggle_bit_uint16,                    \
    uint16_t*: atomic_toggle_bit_uint16,                             \
    volatile uint32_t*: atomic_toggle_bit_uint32,                    \
    uint32_t*: atomic_toggle_bit_uint32,                             \
    volatile int*: atomic_toggle_bit_int,                            \
    int*: atomic_toggle_bit_int                                      \
)(ptr, bit)

#ifdef __cplusplus
}
#endif

#endif // ATOMIC_UTILS_H
