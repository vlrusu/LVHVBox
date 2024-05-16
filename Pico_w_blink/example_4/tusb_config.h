
// **************************************************************************
// *                                                                        *
// *    GenUsb USB Configuration for PicoPython                             *
// *                                                                        *
// **************************************************************************

// The MIT License (MIT)
//
// Copyright 2021-2022, "Hippy"
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to
// deal in the Software without restriction, including without limitation the
// rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
// sell copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
// OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
// THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
// FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
// IN THE SOFTWARE.

#ifndef _TUSB_CONFIG_H_
#define _TUSB_CONFIG_H_

#ifdef __cplusplus
extern "C" {
#endif

// .------------------------------------------------------------------------.
// |    Virtual UART ports (CDC)                                            |
// `------------------------------------------------------------------------'

#define CFG_TUD_CDC             (2)

#define CFG_TUD_CDC_RX_BUFSIZE  (256)
#define CFG_TUD_CDC_TX_BUFSIZE  (256)

// .------------------------------------------------------------------------.
// |    WebUSB (WEB)                                                        |
// `------------------------------------------------------------------------'

#define CFG_TUD_WEB             (0)

// .------------------------------------------------------------------------.
// |    Network (NET)                                                       |
// `------------------------------------------------------------------------'

#define CFG_TUD_NET             (0)

// .------------------------------------------------------------------------.
// |    Mass Storage Device (MSC)                                           |
// `------------------------------------------------------------------------'

#define CFG_TUD_MSC             (0)

#define CFG_TUD_MSC_READONLY    (0)
#define CFG_TUD_MSC_BLOCKS      (16)
#define CFG_TUD_MSC_BUFSIZE     (512)
#define CFG_TUD_MSC_FAT         (12)

// .------------------------------------------------------------------------.
// |    HID Device (HID)                                                    |
// `------------------------------------------------------------------------'

#define CFG_TUD_HID_KEYBOARD    (0)
#define CFG_TUD_HID_MOUSE       (0)
#define CFG_TUD_HID_MOUSE_ABS   (0)
#define CFG_TUD_HID_GAMEPAD     (0)
#define CFG_TUD_HID_CONSUMER    (0)

// .------------------------------------------------------------------------.
// |    MIDI Device (MIDI)                                                  |
// `------------------------------------------------------------------------'

#define CFG_TUD_MIDI            (0)

// .------------------------------------------------------------------------.
// |    Audio Device (AUDIO)                                                |
// `------------------------------------------------------------------------'

#define CFG_TUD_AUDIO           (0)

// .------------------------------------------------------------------------.
// |    Bluetooth Device (BTH)                                              |
// `------------------------------------------------------------------------'

#define CFG_TUD_BTH             (0)

// .------------------------------------------------------------------------.
// |    Test and Measurement Class (TMC)                                    |
// `------------------------------------------------------------------------'

#define CFG_TUD_TMC             (0)

// .------------------------------------------------------------------------.
// |    Reset Handler (RST)                                                 |
// `------------------------------------------------------------------------'

#define CFG_TUD_RST             (0) // ENABLE_PICOPYTHON_BOOT_BAUD

// .------------------------------------------------------------------------.
// |    Generic User Display (GUD)                                          |
// `------------------------------------------------------------------------'

#define CFG_TUD_GUD             (0)

// .------------------------------------------------------------------------.
// |    Vendor Commands (VENDOR)                                            |
// `------------------------------------------------------------------------'

#define CFG_TUD_VENDOR          (0)

// **************************************************************************
// *                                                                        *
// *    Auto-configuration                                                  *
// *                                                                        *
// **************************************************************************

#define CFG_TUSB_RHPORT0_MODE   (OPT_MODE_DEVICE)

// .------------------------------------------------------------------------.
// |    Allow maximum number of endpoints                                   |
// `------------------------------------------------------------------------'

#define CFG_TUD_EP_MAX          (16)

// .------------------------------------------------------------------------.
// |    Support Virtual UART ports (CDC)                                    |
// `------------------------------------------------------------------------'

#if CFG_TUD_CDC
#endif

// .------------------------------------------------------------------------.
// |    Support WebUSB (WEB)                                                |
// `------------------------------------------------------------------------'

#if CFG_TUD_WEB
#endif

// .------------------------------------------------------------------------.
// |    Support Network (NET)                                               |
// `------------------------------------------------------------------------'

#if CFG_TUD_NET
#endif

// TinyUSB changed the name but we didn't

#define CFG_TUD_ECM_RNDIS       CFG_TUD_NET

// .------------------------------------------------------------------------.
// |    Support Mass Storage Device (MSC)                                   |
// `------------------------------------------------------------------------'

#if CFG_TUD_MSC
    #if MICROPY_HW_USB_MSC
        #error "Cannot enable 'MICROPY_HW_USB_MSC' and use own MSC"
    #endif
#endif

#if MICROPY_HW_USB_MSC
    // Ignore the settings we have provided above
    #undef  CFG_TUD_MSC
    #undef  CFG_TUD_MSC_BUFSIZE
    // Provide the settings expected
    #define CFG_TUD_MSC           (1)
    #define CFG_TUD_MSC_BUFSIZE   (MICROPY_FATFS_MAX_SS)
#endif

// .------------------------------------------------------------------------.
// |    Support HID Device (HID)                                            |
// `------------------------------------------------------------------------'

#define XXX_ID_KEYBOARD         (CFG_TUD_HID_KEYBOARD                     )
#define XXX_ID_MOUSE            (CFG_TUD_HID_MOUSE     + XXX_ID_KEYBOARD  )
#define XXX_ID_MOUSE_ABS        (CFG_TUD_HID_MOUSE_ABS + XXX_ID_MOUSE     )
#define XXX_ID_GAMEPAD          (CFG_TUD_HID_GAMEPAD   + XXX_ID_MOUSE_ABS )
#define XXX_ID_CONSUMER         (CFG_TUD_HID_CONSUMER  + XXX_ID_GAMEPAD   )
#define XXX_ID_MAX              (                        XXX_ID_CONSUMER  )

#if XXX_ID_MAX > 0
    #define CFG_TUD_HID         (1)
#else
    #define CFG_TUD_HID         (0)
#endif

#if CFG_TUD_HID
    #define CFG_TUD_HID_BUFSIZE (16)
#endif

#if CFG_TUD_HID_KEYBOARD
    #define REPORT_ID_KEYBOARD  (XXX_ID_KEYBOARD)
#endif
#if CFG_TUD_HID_MOUSE
    #define REPORT_ID_MOUSE     (XXX_ID_MOUSE)
#endif
#if CFG_TUD_HID_MOUSE_ABS
    #define REPORT_ID_MOUSE_ABS (XXX_ID_MOUSE_ABS)
#endif
#if CFG_TUD_HID_GAMEPAD
    #define REPORT_ID_GAMEPAD   (XXX_ID_GAMEPAD)
#endif
#if CFG_TUD_HID_CONSUMER
    #define REPORT_ID_CONSUMER  (XXX_ID_CONSUMER)
#endif

#if CFG_TUD_HID
    #define REPORT_ID_MIN       (1)
    #define REPORT_ID_MAX       (XXX_ID_MAX)
#endif

// .------------------------------------------------------------------------.
// |    Support MIDI Device (MIDI)                                          |
// `------------------------------------------------------------------------'

#if CFG_TUD_MIDI
#endif

// .------------------------------------------------------------------------.
// |    Support Audio Device (AUDIO)                                        |
// `------------------------------------------------------------------------'

#if CFG_TUD_AUDIO
#endif

// .------------------------------------------------------------------------.
// |    Support Bluetooth Device (BTH)                                      |
// `------------------------------------------------------------------------'

#if CFG_TUD_BTH
#endif

// .------------------------------------------------------------------------.
// |    Support Test and Measurement Class (TMC)                            |
// `------------------------------------------------------------------------'

#if CFG_TUD_TMC
#endif

// .------------------------------------------------------------------------.
// |    Support Reset Handler (RST)                                         |
// `------------------------------------------------------------------------'

#if CFG_TUD_RST
    #if CFG_TUD_GUD
        #error "Cannot enable 'RST' (BOOT_USB) when 'GUD' enabled"
    #endif
    #if CFG_TUD_VENDOR
        #error "Cannot enable 'RST' (BOOT_USB) when 'VENDOR' enabled"
    #endif
#endif

// .------------------------------------------------------------------------.
// |    Support Generic User Display (GUD)                                  |
// `------------------------------------------------------------------------'

#if CFG_TUD_GUD
    #if CFG_TUD_RST
        #error "Cannot enable 'GUD' when 'RST' (BOOT_USB) enabled"
    #endif
    #if CFG_TUD_VENDOR
        #error "Cannot enable 'GUD' when 'VENDOR' enabled"
    #endif
#endif

// .------------------------------------------------------------------------.
// |    Support Vendor Commands (VENDOR)                                    |
// `------------------------------------------------------------------------'

#if CFG_TUD_VENDOR
    #if CFG_TUD_RST
        #error "Cannot enable 'VENDOR' when 'RST' (BOOT_USB) enabled"
    #endif
    #if CFG_TUD_GUD
        #error "Cannot enable 'VENDOR' when 'GUD' enabled"
    #endif
#endif

// **************************************************************************
// *                                                                        *
// *    Configuration checking                                              *
// *                                                                        *
// **************************************************************************

// .------------------------------------------------------------------------.
// |    Check Virtual UART ports (CDC)                                      |
// `------------------------------------------------------------------------'

#if CFG_TUD_CDC
    #if   CFG_TUD_CDC < 0
        #error "Cannot set 'CFG_TUD_CDC' negative"
    #elif CFG_TUD_CDC > 6
        #error "Cannot set 'CFG_TUD_CDC' higher than 6"
    #endif
#endif

// .------------------------------------------------------------------------.
// |    Check WebUSB (WEB)                                                  |
// `------------------------------------------------------------------------'

#if CFG_TUD_WEB
    #if   CFG_TUD_WEB < 0
        #error "Cannot set 'CFG_TUD_WEB' negative"
    #elif CFG_TUD_WEB > 1
        #error "Cannot set 'CFG_TUD_WEB' higher than 1"
    #endif
#endif

// .------------------------------------------------------------------------.
// |    Check Network (NET)                                                 |
// `------------------------------------------------------------------------'

#if CFG_TUD_NET
    #if   CFG_TUD_NET < 0
        #error "Cannot set 'CFG_TUD_NET' negative"
    #elif CFG_TUD_NET > 1
        #error "Cannot set 'CFG_TUD_NET' higher than 1"
    #endif
#endif

// .------------------------------------------------------------------------.
// |    Check Mass Storage Device (MSC)                                     |
// `------------------------------------------------------------------------'

#if CFG_TUD_MSC
    #if   CFG_TUD_MSC < 0
        #error "Cannot set 'CFG_TUD_MSC' negative"
    #elif CFG_TUD_MSC > 1
        #error "Cannot set 'CFG_TUD_MSC' higher than 1"
    #endif
#endif

// .------------------------------------------------------------------------.
// |    Check HID Device (HID)                                              |
// `------------------------------------------------------------------------'

#if CFG_TUD_HID
    #if   CFG_TUD_HID < 0
        #error "Cannot set 'CFG_TUD_HID' negative"
    #elif CFG_TUD_HID > 1
        #error "Cannot set 'CFG_TUD_HID' higher than 1"
    #endif
#endif

// .------------------------------------------------------------------------.
// |    Check MIDI Device (MIDI)                                            |
// `------------------------------------------------------------------------'

#if CFG_TUD_MIDI
    #if   CFG_TUD_MIDI < 0
        #error "Cannot set 'CFG_TUD_MIDI' negative"
    #elif CFG_TUD_MIDI > 1
        #error "Cannot set 'CFG_TUD_MIDI' higher than 1"
    #endif
#endif

// .------------------------------------------------------------------------.
// |    Check Audio Device (AUDIO)                                          |
// `------------------------------------------------------------------------'

#if CFG_TUD_AUDIO
    #if   CFG_TUD_AUDIO < 0
        #error "Cannot set 'CFG_TUD_AUDIO' negative"
    #elif CFG_TUD_AUDIO > 1
        #error "Cannot set 'CFG_TUD_AUDIO' higher than 1"
    #endif
#endif

// .------------------------------------------------------------------------.
// |    Check Bluetooth Device (BTH)                                        |
// `------------------------------------------------------------------------'

#if CFG_TUD_BTH
    #if   CFG_TUD_BTH < 0
        #error "Cannot set 'CFG_TUD_BTH' negative"
    #elif CFG_TUD_BTH > 1
        #error "Cannot set 'CFG_TUD_BTH' higher than 1"
    #endif
#endif

// .------------------------------------------------------------------------.
// |    Check Test and Measurement Class (TMC)                              |
// `------------------------------------------------------------------------'

#if CFG_TUD_TMC
    #if   CFG_TUD_TMC < 0
        #error "Cannot set 'CFG_TUD_TMC' negative"
    #elif CFG_TUD_TMC > 1
        #error "Cannot set 'CFG_TUD_TMC' higher than 1"
    #endif
#endif

// .------------------------------------------------------------------------.
// |    Check Generic User Display (GUD)                                    |
// `------------------------------------------------------------------------'

#if CFG_TUD_GUD
    #if   CFG_TUD_GUD < 0
        #error "Cannot set 'CFG_TUD_GUD' negative"
    #elif CFG_TUD_GUD > 1
        #error "Cannot set 'CFG_TUD_GUD' higher than 1"
    #endif
#endif

// .------------------------------------------------------------------------.
// |    Check Reset Handler (RST)                                           |
// `------------------------------------------------------------------------'

#if CFG_TUD_RST
    #if   CFG_TUD_RST < 0
        #error "Cannot set 'CFG_TUD_RST' negative"
    #elif CFG_TUD_RST > 1
        #error "Cannot set 'CFG_TUD_RST' higher than 1"
    #endif
#endif

// .------------------------------------------------------------------------.
// |    Check Vendor Commands (VENDOR)                                      |
// `------------------------------------------------------------------------'

#if CFG_TUD_VENDOR
    #if   CFG_TUD_VENDOR < 0
        #error "Cannot set 'CFG_TUD_VENDOR' negative"
    #elif CFG_TUD_VENDOR > 1
        #error "Cannot set 'CFG_TUD_VENDOR' higher than 1"
    #endif
#endif

// **************************************************************************
// *                                                                        *
// *    VID Definition                                                      *
// *                                                                        *
// **************************************************************************

#define GENUSB_MANUFACTURER     "PicoPython"

#define GENUSB_VID              0x2E8A  // Raspberry Pi

// **************************************************************************
// *                                                                        *
// *    PID Definition                                                      *
// *                                                                        *
// **************************************************************************

// The default TinyUSB PID is -
//
//    01-- ---- --nv ihmc
//
// But we want to allow multiple CDC channels so we use -
//
//    11-g vtbn maih wccc               // 5432 1-98 7654 3210
//                                      //
//                                      // 11-g vtbn maih wccc
                                        //    | |||| |||| | |
#define PID_SHL_CDC             0       //    | |||| |||| | `------  CDC
#define PID_SHL_WEB             3       //    | |||| |||| `--------  WEB
#define PID_SHL_HID             4       //    | |||| |||`----------  HID
#define PID_SHL_MIDI            5       //    | |||| ||`-----------  MIDI
#define PID_SHL_AUDIO           6       //    | |||| |`------------  AUDIO
#define PID_SHL_MSC             7       //    | |||| `-------------  MSC
#define PID_SHL_NET             8       //    | |||`---------------  NET
#define PID_SHL_BTH             9       //    | ||`----------------  BTH
#define PID_SHL_TMC             10      //    | |`-----------------  TMC
#define PID_SHL_VENDOR          11      //    | `------------------  VENDOR
#define PID_SHL_GUD             12      //    `--------------------  GUD

#define GENUSB_PID              (( 0xC000                           ) | \
                                 ( CFG_TUD_CDC    << PID_SHL_CDC    ) | \
                                 ( CFG_TUD_WEB    << PID_SHL_WEB    ) | \
                                 ( CFG_TUD_HID    << PID_SHL_HID    ) | \
                                 ( CFG_TUD_MIDI   << PID_SHL_MIDI   ) | \
                                 ( CFG_TUD_AUDIO  << PID_SHL_AUDIO  ) | \
                                 ( CFG_TUD_MSC    << PID_SHL_MSC    ) | \
                                 ( CFG_TUD_NET    << PID_SHL_NET    ) | \
                                 ( CFG_TUD_BTH    << PID_SHL_BTH    ) | \
                                 ( CFG_TUD_TMC    << PID_SHL_TMC    ) | \
                                 ( CFG_TUD_VENDOR << PID_SHL_VENDOR ) | \
                                 ( CFG_TUD_GUD    << PID_SHL_GUD    ))

// **************************************************************************
// *                                                                        *
// *    Device Definition                                                   *
// *                                                                        *
// **************************************************************************

// We encode our functionality in 'bcdDevice' as well as PID -
//
//    -awg tvbn -mih -ccc               // 5432 1-98 7654 3210
//                                      //
//                                      // -awg tvbn -mih -ccc
                                        //  ||| ||||  |||   |
#define DEV_SHL_CDC             0       //  ||| ||||  |||   `------  CDC
#define DEV_SHL_WEB             13      //  |`|-||||--|||----------  WEB
#define DEV_SHL_HID             4       //  | | ||||  ||`----------  HID
#define DEV_SHL_MIDI            5       //  | | ||||  |`-----------  MIDI
#define DEV_SHL_AUDIO           14      //  `-|-||||--|------------  AUDIO
#define DEV_SHL_MSC             6       //    | ||||  `------------  MSC
#define DEV_SHL_NET             8       //    | |||`---------------  NET
#define DEV_SHL_BTH             9       //    | ||`----------------  BTH
#define DEV_SHL_TMC             11      //    | `|-----------------  TMC
#define DEV_SHL_VENDOR          10      //    |  `-----------------  VENDOR
#define DEV_SHL_GUD             12      //    `--------------------  GUD

#define GENUSB_DEV              (( CFG_TUD_CDC    << DEV_SHL_CDC    ) | \
                                 ( CFG_TUD_WEB    << DEV_SHL_WEB    ) | \
                                 ( CFG_TUD_HID    << DEV_SHL_HID    ) | \
                                 ( CFG_TUD_MIDI   << DEV_SHL_MIDI   ) | \
                                 ( CFG_TUD_AUDIO  << DEV_SHL_AUDIO  ) | \
                                 ( CFG_TUD_MSC    << DEV_SHL_MSC    ) | \
                                 ( CFG_TUD_NET    << DEV_SHL_NET    ) | \
                                 ( CFG_TUD_BTH    << DEV_SHL_BTH    ) | \
                                 ( CFG_TUD_TMC    << DEV_SHL_TMC    ) | \
                                 ( CFG_TUD_VENDOR << DEV_SHL_VENDOR ) | \
                                 ( CFG_TUD_GUD    << DEV_SHL_GUD    ))

// **************************************************************************
// *                                                                        *
// *    USB Product Name                                                    *
// *                                                                        *
// **************************************************************************

#if GENUSB_PID > 0xC008
    #define TAG_CDC_PREFIX      "-"
#else
    #define TAG_CDC_PREFIX      ""
#endif

#if   CFG_TUD_CDC >= 6
    #define TAG_CDC     TAG_CDC_PREFIX "6C"
#elif CFG_TUD_CDC >= 5
    #define TAG_CDC     TAG_CDC_PREFIX "5C"
#elif CFG_TUD_CDC >= 4
    #define TAG_CDC     TAG_CDC_PREFIX "4C"
#elif CFG_TUD_CDC >= 3
    #define TAG_CDC     TAG_CDC_PREFIX "3C"
#elif CFG_TUD_CDC >= 2
    #define TAG_CDC     TAG_CDC_PREFIX "2C"
#elif CFG_TUD_CDC >= 1
    #define TAG_CDC     TAG_CDC_PREFIX "1C"
#else
    #define TAG_CDC     ""
#endif

#if CFG_TUD_WEB
    #define TAG_WEB     "W"
#else
    #define TAG_WEB     ""
#endif

#if CFG_TUD_HID
    #define TAG_HID     "H"
#else
    #define TAG_HID     ""
#endif

#if CFG_TUD_MIDI
    #define TAG_MIDI    "I"
#else
    #define TAG_MIDI    ""
#endif

#if CFG_TUD_AUDIO
    #define TAG_AUDIO   "A"
#else
    #define TAG_AUDIO   ""
#endif

#if CFG_TUD_MSC
    #define TAG_MSC     "M"
#else
    #define TAG_MSC     ""
#endif

#if CFG_TUD_NET
    #define TAG_NET     "N"
#else
    #define TAG_NET     ""
#endif

#if CFG_TUD_BTH
    #define TAG_BTH     "B"
#else
    #define TAG_BTH     ""
#endif

#if CFG_TUD_TMC
    #define TAG_TMC     "T"
#else
    #define TAG_TMC     ""
#endif

#if CFG_TUD_RST
    // No tag entry
#endif

#if CFG_TUD_GUD
    #if GENUSB_PID > 0xD008
      #define TAG_GUD   "GUD-"
    #else
      #define TAG_GUD   "GUD"
    #endif
#else
      #define TAG_GUD   ""
#endif

#if CFG_TUD_VENDOR
    #define TAG_VENDOR  "V"
#else
    #define TAG_VENDOR  ""
#endif

#define GENUSB_PRODUCT  "GenUsb-"  \
                        TAG_GUD    \
                        TAG_VENDOR \
                        TAG_TMC    \
                        TAG_BTH    \
                        TAG_NET    \
                        TAG_MSC    \
                        TAG_AUDIO  \
                        TAG_MIDI   \
                        TAG_HID    \
                        TAG_WEB    \
                        TAG_CDC

// **************************************************************************
// *                                                                        *
// *    End of USB configuration                                            *
// *                                                                        *
// **************************************************************************

#endif
