
// **************************************************************************
// *                                                                        *
// *    GenUsb USB Descriptors for PicoPython                               *
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

#include "tusb.h"
#include "pico/unique_id.h"
#include "pico/binary_info.h"

// **************************************************************************
// *                                                                        *
// *    Binary Information for Picotool                                     *
// *                                                                        *
// **************************************************************************

#define BI_GU_TAG               BINARY_INFO_MAKE_TAG('G', 'U')
#define BI_GU_ID                0x95639AC7
#define BI_GU_ITF(itf)          bi_decl(bi_string(BI_GU_TAG, BI_GU_ID, itf))
#define BI_GU_TXT(txt)          bi_decl(bi_program_feature(txt))

bi_decl(bi_program_feature_group_with_flags(
        BI_GU_TAG, BI_GU_ID, "genusb options",
        BI_NAMED_GROUP_SEPARATE_COMMAS | BI_NAMED_GROUP_SORT_ALPHA));

BI_GU_TXT("GenUsb device descriptor - " GENUSB_PRODUCT)

#if   CFG_TUD_CDC >= 6
    BI_GU_ITF("CDC x 6")
#elif CFG_TUD_CDC >= 5
    BI_GU_ITF("CDC x 5")
#elif CFG_TUD_CDC >= 4
    BI_GU_ITF("CDC x 4")
#elif CFG_TUD_CDC >= 3
    BI_GU_ITF("CDC x 3")
#elif CFG_TUD_CDC >= 2
    BI_GU_ITF("CDC x 2")
#elif CFG_TUD_CDC >= 1
    BI_GU_ITF("CDC")
#endif

#if CFG_TUD_WEB
    BI_GU_ITF("WEB")
#endif

#if CFG_TUD_HID_KEYBOARD
    BI_GU_ITF("HID KEYBOARD")
#endif
#if CFG_TUD_HID_MOUSE
    BI_GU_ITF("HID MOUSE")
#endif
#if CFG_TUD_HID_MOUSE_ABS
    BI_GU_ITF("HID MOUSE ABS")
#endif
#if CFG_TUD_HID_GAMEPAD
    BI_GU_ITF("HID GAMEPAD")
#endif
#if CFG_TUD_HID_CONSUMER
    BI_GU_ITF("HID CONSUMER")
#endif

#if CFG_TUD_MIDI
    BI_GU_ITF("MIDI")
#endif

#if CFG_TUD_AUDIO
    BI_GU_ITF("AUDIO")
#endif

#if CFG_TUD_MSC
    BI_GU_ITF("MSC")
#endif

#if CFG_TUD_NET
    BI_GU_ITF("NET")
#endif

#if CFG_TUD_BTH
    BI_GU_ITF("BTH")
#endif

#if CFG_TUD_TMC
    BI_GU_ITF("TMC")
#endif

#if CFG_TUD_RST
    BI_GU_ITF("RST")
#endif

#if CFG_TUD_GUD
    BI_GU_ITF("GUD")
#endif

#if CFG_TUD_VENDOR
    BI_GU_ITF("VENDOR")
#endif

// **************************************************************************
// *                                                                        *
// *    USB Device Descriptor Strings                                       *
// *                                                                        *
// **************************************************************************

enum {
    USBD_STR_LANGUAGE,
    USBD_STR_MANUFACTURER,
    USBD_STR_PRODUCT,
    USBD_STR_SERIAL_NUMBER,
#if CFG_TUD_CDC > 0
    USBD_STR_CDC_0_NAME,
#endif
#if CFG_TUD_CDC > 1
    USBD_STR_CDC_1_NAME,
#endif
#if CFG_TUD_CDC > 2
    USBD_STR_CDC_2_NAME,
#endif
#if CFG_TUD_CDC > 3
    USBD_STR_CDC_3_NAME,
#endif
#if CFG_TUD_CDC > 4
    USBD_STR_CDC_4_NAME,
#endif
#if CFG_TUD_CDC > 5
    USBD_STR_CDC_5_NAME,
#endif
#if CFG_TUD_CDC > 6
    USBD_STR_CDC_6_NAME,
#endif
#if CFG_TUD_WEB
    USBD_STR_WEB_NAME,
#endif
#if CFG_TUD_HID
    USBD_STR_HID_NAME,
#endif
#if CFG_TUD_MIDI
    USBD_STR_MIDI_NAME,
#endif
#if CFG_TUD_AUDIO
    USBD_STR_AUDIO_NAME,
#endif
#if CFG_TUD_MSC
    USBD_STR_MSC_NAME,
#endif
#if CFG_TUD_NET
    USBD_STR_NET_NAME,
    USBD_STR_NET_MAC_ADDR,
#endif
#if CFG_TUD_BTH
    USBD_STR_BTH_NAME,
#endif
#if CFG_TUD_TMC
    USBD_STR_TMC_NAME,
#endif
#if CFG_TUD_RST
    USBD_STR_RST_NAME,
#endif
#if CFG_TUD_GUD
    USBD_STR_GUD_NAME,
#endif
#if CFG_TUD_VENDOR
    USBD_STR_VENDOR_NAME,
#endif
};

char *const usbd_desc_str[] = {
    [USBD_STR_MANUFACTURER]     = GENUSB_MANUFACTURER,
    [USBD_STR_PRODUCT]          = GENUSB_PRODUCT,
    [USBD_STR_SERIAL_NUMBER]    = NULL,
#if CFG_TUD_CDC > 0
    [USBD_STR_CDC_0_NAME]       = "REPL",
#endif
#if CFG_TUD_CDC > 1
    [USBD_STR_CDC_1_NAME]       = "DATA",
#endif
#if CFG_TUD_CDC > 2
    [USBD_STR_CDC_2_NAME]       = "CDC2",
#endif
#if CFG_TUD_CDC > 3
    [USBD_STR_CDC_3_NAME]       = "CDC3",
#endif
#if CFG_TUD_CDC > 4
    [USBD_STR_CDC_4_NAME]       = "CDC4",
#endif
#if CFG_TUD_CDC > 5
    [USBD_STR_CDC_5_NAME]       = "CDC5",
#endif
#if CFG_TUD_CDC > 6
    [USBD_STR_CDC_6_NAME]       = "CDC6",
#endif
#if CFG_TUD_WEB
    [USBD_STR_WEB_NAME]         = "WEB",
#endif
#if CFG_TUD_HID
    [USBD_STR_HID_NAME]         = "HID",
#endif
#if CFG_TUD_MIDI
    [USBD_STR_MIDI_NAME]        = "MIDI",
#endif
#if CFG_TUD_AUDIO
    [USBD_STR_AUDIO_NAME]       = "AUDIO",
#endif
#if CFG_TUD_MSC
    [USBD_STR_MSC_NAME]         = "MSC",
#endif
#if CFG_TUD_NET
    [USBD_STR_NET_NAME]         = "NET",
    [USBD_STR_NET_MAC_ADDR]     = NULL,
#endif
#if CFG_TUD_BTH
    [USBD_STR_BTH_NAME]         = "BTH",
#endif
#if CFG_TUD_TMC
    [USBD_STR_TMC_NAME]         = "TMC",
#endif
#if CFG_TUD_RST
    [USBD_STR_RST_NAME]         = "Reset",
#endif
#if CFG_TUD_GUD
    [USBD_STR_GUD_NAME]         = "GUD",
#endif
#if CFG_TUD_VENDOR
    [USBD_STR_VENDOR_NAME]      = "VENDOR",
#endif
};

// **************************************************************************
// *                                                                        *
// *    Device Descriptor                                                   *
// *                                                                        *
// **************************************************************************

static const tusb_desc_device_t usbd_desc_device = {
    .bLength                    = sizeof(tusb_desc_device_t),
    .bDescriptorType            = TUSB_DESC_DEVICE,
    .bcdUSB                     = 0x0200,
    .bDeviceClass               = TUSB_CLASS_MISC,
    .bDeviceSubClass            = MISC_SUBCLASS_COMMON,
    .bDeviceProtocol            = MISC_PROTOCOL_IAD,
    .bMaxPacketSize0            = CFG_TUD_ENDPOINT0_SIZE,
    .idVendor                   = GENUSB_VID,
    .idProduct                  = GENUSB_PID,
    .bcdDevice                  = GENUSB_DEV,
    .iManufacturer              = USBD_STR_MANUFACTURER,
    .iProduct                   = USBD_STR_PRODUCT,
    .iSerialNumber              = USBD_STR_SERIAL_NUMBER,
    .bNumConfigurations         = 1,
};

// **************************************************************************
// *                                                                        *
// *    Endpoint Definitions                                                *
// *                                                                        *
// **************************************************************************

#define EPNUM_BASE_WEB          (( 2 * CFG_TUD_CDC   ) + 0x81             )
#define EPNUM_BASE_HID          ((     CFG_TUD_WEB   ) + EPNUM_BASE_WEB   )
#define EPNUM_BASE_MIDI         ((     CFG_TUD_HID   ) + EPNUM_BASE_HID   )
#define EPNUM_BASE_AUDIO        ((     CFG_TUD_MIDI  ) + EPNUM_BASE_MIDI  )
#define EPNUM_BASE_MSC          ((     CFG_TUD_AUDIO ) + EPNUM_BASE_AUDIO )
#define EPNUM_BASE_NET          ((     CFG_TUD_MSC   ) + EPNUM_BASE_MSC   )
#define EPNUM_BASE_BTH          (( 2 * CFG_TUD_NET   ) + EPNUM_BASE_NET   )
#define EPNUM_BASE_TMC          ((     CFG_TUD_BTH   ) + EPNUM_BASE_BTH   )
#define EPNUM_BASE_VENDOR       ((     CFG_TUD_TMC   ) + EPNUM_BASE_TMC   )

#if   EEPNUM_BASE_VENDOR == 0x81
    #error "No interfaces defined"
#elif EEPNUM_BASE_VENDOR >  0x8F
    #error "Too many interfaces defined"
#endif

// .------------------------------------------------------------------------.
// |    Support Virtual Serial Ports (CDC)                                  |
// `------------------------------------------------------------------------'

#if CFG_TUD_CDC > 0
    #define EPNUM_CDC_0_CMD     (0x81)
    #define EPNUM_CDC_0_DATA    (0x82)
#endif
#if CFG_TUD_CDC > 1
    #define EPNUM_CDC_1_CMD     (0x83)
    #define EPNUM_CDC_1_DATA    (0x84)
#endif
#if CFG_TUD_CDC > 2
    #define EPNUM_CDC_2_CMD     (0x85)
    #define EPNUM_CDC_2_DATA    (0x86)
#endif
#if CFG_TUD_CDC > 3
    #define EPNUM_CDC_3_CMD     (0x87)
    #define EPNUM_CDC_3_DATA    (0x88)
#endif
#if CFG_TUD_CDC > 4
    #define EPNUM_CDC_4_CMD     (0x89)
    #define EPNUM_CDC_4_DATA    (0x8A)
#endif
#if CFG_TUD_CDC > 5
    #define EPNUM_CDC_5_CMD     (0x8B)
    #define EPNUM_CDC_5_DATA    (0x8C)
#endif
#if CFG_TUD_CDC > 6
    #define EPNUM_CDC_6_CMD     (0x8D)
    #define EPNUM_CDC_6_DATA    (0x8E)
#endif

// .------------------------------------------------------------------------.
// |    Support WebUSB (WEB)                                                |
// `------------------------------------------------------------------------'

#if CFG_TUD_WEB
    #define EPNUM_WEB_DATA      (EPNUM_BASE_WEB)
#endif

// .------------------------------------------------------------------------.
// |    Support Network (NET)                                               |
// `------------------------------------------------------------------------'

#if CFG_TUD_NET
    #define EPNUM_NET_CMD       (EPNUM_BASE_NET + 0)
    #define EPNUM_NET_DATA      (EPNUM_BASE_NET + 1)
#endif

// .------------------------------------------------------------------------.
// |    Support Mass Storage Device (MSC)                                   |
// `------------------------------------------------------------------------'

#if CFG_TUD_MSC
    #define EPNUM_MSC_DATA      (EPNUM_BASE_MSC)
#endif

// .------------------------------------------------------------------------.
// |    Support HID Device (HID)                                            |
// `------------------------------------------------------------------------'

#if CFG_TUD_HID
    #define EPNUM_HID_DATA      (EPNUM_BASE_HID)
#endif

// .------------------------------------------------------------------------.
// |    Support MIDI Device (MIDI)                                          |
// `------------------------------------------------------------------------'

#if CFG_TUD_MIDI
    #define EPNUM_MIDI_DATA     (EPNUM_BASE_MIDI)
#endif

// .------------------------------------------------------------------------.
// |    Support Audio Device (AUDIO)                                        |
// `------------------------------------------------------------------------'

#if CFG_TUD_AUDIO
    #define EPNUM_AUDIO_DATA    (EPNUM_BASE_AUDIO)
#endif

// .------------------------------------------------------------------------.
// |    Support Bluetooth Device (BTH)                                      |
// `------------------------------------------------------------------------'

#if CFG_TUD_BTH
    #define EPNUM_BTH_DATA      (EPNUM_BASE_BTH)
#endif

// .------------------------------------------------------------------------.
// |    Support Test and Measurement Class (TMC)                            |
// `------------------------------------------------------------------------'

#if CFG_TUD_TMC
    #define EPNUM_TMC_DATA      (EPNUM_BASE_MSC)
#endif

// .------------------------------------------------------------------------.
// |    Support Reset Handler (RST)                                         |
// `------------------------------------------------------------------------'

#if CFG_TUD_RST
     #include "pico-sdk/reset_interface.h"
#endif

// .------------------------------------------------------------------------.
// |    Support Generic USB Display (GUD)                                   |
// `------------------------------------------------------------------------'

#if CFG_TUD_GUD
    #define EPNUM_GUD_DATA      (EPNUM_BASE_VENDOR)
#endif

// .------------------------------------------------------------------------.
// |    Support Vendor Commands (VENDOR)                                    |
// `------------------------------------------------------------------------'

#if CFG_TUD_VENDOR
    #define EPNUM_VENDOR_DATA   (EPNUM_BASE_VENDOR)
#endif

// **************************************************************************
// *                                                                        *
// *    Device Configuration                                                *
// *                                                                        *
// **************************************************************************

#define USBD_MAX_POWER_MA       (250)

#define TUD_RST_DESC_LEN        (9)

#define USBD_DESC_LEN           (TUD_CONFIG_DESC_LEN                      ) + \
                                (TUD_CDC_DESC_LEN        * CFG_TUD_CDC    ) + \
                                (TUD_BOS_WEBUSB_DESC_LEN * CFG_TUD_WEB    ) + \
                                (TUD_HID_DESC_LEN        * CFG_TUD_HID    ) + \
                                (TUD_MIDI_DESC_LEN       * CFG_TUD_MIDI   ) + \
                          /* (TUD_AUDIO_DESC_LEN      * CFG_TUD_AUDIO  ) + */ \
                                (TUD_MSC_DESC_LEN        * CFG_TUD_MSC    ) + \
                                (TUD_RNDIS_DESC_LEN      * CFG_TUD_NET    ) + \
                                (TUD_BTH_DESC_LEN        * CFG_TUD_BTH    ) + \
                          /* (TUD_TMC_DESC_LEN        * CFG_TUD_TMC    ) + */ \
                                (TUD_RST_DESC_LEN        * CFG_TUD_RST    ) + \
                          /* (TUD_GUD_DESC_LEN        * CFG_TUD_GUD    ) + */ \
                                (TUD_VENDOR_DESC_LEN     * CFG_TUD_VENDOR )

#if CFG_TUD_AUDIO
    #error "No 'TUD_AUDIO_DESC_LEN' exists"
#endif
#if CFG_TUD_TMC
    #error "No 'TUD_TMC_DESC_LEN' exists"
#endif
#if CFG_TUD_GUD
    #error "No 'TUD_GUD_DESC_LEN' exists"
#endif

// **************************************************************************
// *                                                                        *
// *    Interfaces                                                          *
// *                                                                        *
// **************************************************************************

enum {
#if CFG_TUD_CDC > 0
    ITF_NUM_CDC_0, ITF_NUM_CDC_0_DATA,
#endif
#if CFG_TUD_CDC > 1
    ITF_NUM_CDC_1, ITF_NUM_CDC_1_DATA,
#endif
#if CFG_TUD_CDC > 2
    ITF_NUM_CDC_2, ITF_NUM_CDC_2_DATA,
#endif
#if CFG_TUD_CDC > 3
    ITF_NUM_CDC_3, ITF_NUM_CDC_3_DATA,
#endif
#if CFG_TUD_CDC > 4
    ITF_NUM_CDC_4, ITF_NUM_CDC_4_DATA,
#endif
#if CFG_TUD_CDC > 5
    ITF_NUM_CDC_5, ITF_NUM_CDC_5_DATA,
#endif
#if CFG_TUD_CDC > 6
    ITF_NUM_CDC_6, ITF_NUM_CDC_6_DATA,
#endif
#if CFG_TUD_WEB
    ITF_NUM_WEB,
#endif
#if CFG_TUD_HID
    ITF_NUM_HID,
#endif
#if CFG_TUD_MIDI
    ITF_NUM_MIDI,
#endif
#if CFG_TUD_AUDIO
    ITF_NUM_AUDIO,
#endif
#if CFG_TUD_MSC
    ITF_NUM_MSC,
#endif
#if CFG_TUD_NET
    ITF_NUM_NET, ITF_NUM_NET_DATA,
#endif
#if CFG_TUD_BTH
    ITF_NUM_BTH,
#endif
#if CFG_TUD_TMC
    ITF_NUM_TMC,
#endif
#if CFG_TUD_RST
    ITF_NUM_RST,
#endif
#if CFG_TUD_GUD
    ITF_NUM_GUD,
#endif
#if CFG_TUD_VENDOR
    ITF_NUM_VENDOR,
#endif
    ITF_NUM_TOTAL
};

// **************************************************************************
// *                                                                        *
// *    HID descriptor                                                      *
// *                                                                        *
// **************************************************************************

#if CFG_TUD_HID

static const uint8_t desc_hid_report[] = {
#if CFG_TUD_HID_KEYBOARD
    TUD_HID_REPORT_DESC_KEYBOARD  (HID_REPORT_ID(REPORT_ID_KEYBOARD)),
#endif
#if CFG_TUD_HID_MOUSE
    TUD_HID_REPORT_DESC_MOUSE     (HID_REPORT_ID(REPORT_ID_MOUSE)),
#endif
#if CFG_TUD_HID_MOUSE_ABS
    TUD_HID_REPORT_DESC_MOUSE_ABS (HID_REPORT_ID(REPORT_ID_MOUSE_ABS)),
#endif
#if CFG_TUD_HID_GAMEPAD
    TUD_HID_REPORT_DESC_GAMEPAD   (HID_REPORT_ID(REPORT_ID_GAMEPAD)),
#endif
#if CFG_TUD_HID_CONSUMER
    TUD_HID_REPORT_DESC_CONSUMER  (HID_REPORT_ID(REPORT_ID_CONSUMER)),
#endif
};

#endif

// **************************************************************************
// *                                                                        *
// *    Descriptor                                                          *
// *                                                                        *
// **************************************************************************

static const uint8_t usbd_desc_cfg[USBD_DESC_LEN] = {

    TUD_CONFIG_DESCRIPTOR(1, ITF_NUM_TOTAL,
                          USBD_STR_LANGUAGE,
                          USBD_DESC_LEN,
                          TUSB_DESC_CONFIG_ATT_REMOTE_WAKEUP,
                          USBD_MAX_POWER_MA),

// .------------------------------------------------------------------------.
// |    Support Virtual UART ports (CDC)                                    |
// `------------------------------------------------------------------------'

#if CFG_TUD_CDC
    #define USBD_CDC_CMD_SIZE   (64)
    #define USBD_CDC_DATA_SIZE  (64)
#endif

#if CFG_TUD_CDC > 0
    TUD_CDC_DESCRIPTOR(ITF_NUM_CDC_0,
                      USBD_STR_CDC_0_NAME,
                         EPNUM_CDC_0_CMD, USBD_CDC_CMD_SIZE,
                         EPNUM_CDC_0_DATA & 0x7F,
                         EPNUM_CDC_0_DATA, USBD_CDC_DATA_SIZE),
#endif
#if CFG_TUD_CDC > 1
    TUD_CDC_DESCRIPTOR(ITF_NUM_CDC_1,
                      USBD_STR_CDC_1_NAME,
                         EPNUM_CDC_1_CMD, USBD_CDC_CMD_SIZE,
                         EPNUM_CDC_1_DATA & 0x7F,
                         EPNUM_CDC_1_DATA, USBD_CDC_DATA_SIZE),
#endif
#if CFG_TUD_CDC > 2
    TUD_CDC_DESCRIPTOR(ITF_NUM_CDC_2,
                      USBD_STR_CDC_2_NAME,
                         EPNUM_CDC_2_CMD, USBD_CDC_CMD_SIZE,
                         EPNUM_CDC_2_DATA & 0x7F,
                         EPNUM_CDC_2_DATA, USBD_CDC_DATA_SIZE),
#endif
#if CFG_TUD_CDC > 3
    TUD_CDC_DESCRIPTOR(ITF_NUM_CDC_3,
                      USBD_STR_CDC_3_NAME,
                         EPNUM_CDC_3_CMD, USBD_CDC_CMD_SIZE,
                         EPNUM_CDC_3_DATA & 0x7F,
                         EPNUM_CDC_3_DATA, USBD_CDC_DATA_SIZE),
#endif
#if CFG_TUD_CDC > 4
    TUD_CDC_DESCRIPTOR(ITF_NUM_CDC_4,
                      USBD_STR_CDC_4_NAME,
                         EPNUM_CDC_4_CMD, USBD_CDC_CMD_SIZE,
                         EPNUM_CDC_4_DATA & 0x7F,
                         EPNUM_CDC_4_DATA, USBD_CDC_DATA_SIZE),
#endif
#if CFG_TUD_CDC > 5
    TUD_CDC_DESCRIPTOR(ITF_NUM_CDC_5,
                      USBD_STR_CDC_5_NAME,
                         EPNUM_CDC_5_CMD, USBD_CDC_CMD_SIZE,
                         EPNUM_CDC_5_DATA & 0x7F,
                         EPNUM_CDC_5_DATA, USBD_CDC_DATA_SIZE),
#endif
#if CFG_TUD_CDC > 6
    TUD_CDC_DESCRIPTOR(ITF_NUM_CDC_6,
                      USBD_STR_CDC_6_NAME,
                         EPNUM_CDC_6_CMD, USBD_CDC_CMD_SIZE,
                         EPNUM_CDC_6_DATA & 0x7F,
                         EPNUM_CDC_6_DATA, USBD_CDC_DATA_SIZE),
#endif

// .------------------------------------------------------------------------.
// |    Support WebUSB (WEB)                                                |
// `------------------------------------------------------------------------'

#if CFG_TUD_WEB
    #error "No configuration descriptor implemented for 'CFG_TUD_WEB'"
#endif

// .------------------------------------------------------------------------.
// |    Support Network (NET)                                               |
// `------------------------------------------------------------------------'

#if CFG_TUD_NET
    #define USBD_NET_CMD_SIZE   (64)
    #define USBD_NET_DATA_SIZE  (64)
#endif

#if CFG_TUD_NET
    TUD_RNDIS_DESCRIPTOR(ITF_NUM_NET,
                        USBD_STR_NET_NAME,
                           EPNUM_NET_CMD, USBD_NET_CMD_SIZE,
                           EPNUM_NET_DATA & 0x7F,
                           EPNUM_NET_DATA, USBD_NET_DATA_SIZE),
#endif

// .------------------------------------------------------------------------.
// |    Support Mass Storage Device (MSC)                                   |
// `------------------------------------------------------------------------'

#if CFG_TUD_MSC
    #define USBD_MSC_DATA_SIZE  (64)
#endif

#if CFG_TUD_MSC
    TUD_MSC_DESCRIPTOR(ITF_NUM_MSC,
                      USBD_STR_MSC_NAME,
                         EPNUM_MSC_DATA & 0x7F,
                         EPNUM_MSC_DATA, USBD_MSC_DATA_SIZE),
#endif

// .------------------------------------------------------------------------.
// |    Support HID Device (HID)                                            |
// `------------------------------------------------------------------------'

#if CFG_TUD_HID
    #define USBD_HID_BUFSIZE        (16)
    #define USBD_HID_POLL_INTERVAL  (10)
#endif

#if CFG_TUD_HID
    TUD_HID_DESCRIPTOR(ITF_NUM_HID,
                      USBD_STR_HID_NAME, HID_ITF_PROTOCOL_NONE,
                                         sizeof(desc_hid_report),
                         EPNUM_HID_DATA, USBD_HID_BUFSIZE,
                          USBD_HID_POLL_INTERVAL),
#endif

// .------------------------------------------------------------------------.
// |    Support MIDI Device (MIDI)                                          |
// `------------------------------------------------------------------------'

#if CFG_TUD_MIDI
    #error "No configuration descriptor implemented for 'CFG_TUD_MIDI'"
#endif

// .------------------------------------------------------------------------.
// |    Support Audio Device (AUDIO)                                        |
// `------------------------------------------------------------------------'

#if CFG_TUD_AUDIO
    #error "No configuration descriptor implemented for 'CFG_TUD_AUDIO'"
#endif

// .------------------------------------------------------------------------.
// |    Support Bluetooth Device (BTH)                                      |
// `------------------------------------------------------------------------'

#if CFG_TUD_BTH
    #error "No configuration descriptor implemented for 'CFG_TUD_BTH'"
#endif

// .------------------------------------------------------------------------.
// |    Support Test and Measurement Class (TMC)                            |
// `------------------------------------------------------------------------'

#if CFG_TUD_TMC
    #error "No configuration descriptor implemented for 'CFG_TUD_TMC'"
#endif

// .------------------------------------------------------------------------.
// |    Support Reset Handler (RST) / (BOOT_USB)                            |
// `------------------------------------------------------------------------'

#if CFG_TUD_RST

    TUD_RST_DESC_LEN, TUSB_DESC_INTERFACE, ITF_NUM_RST, 0, 0,
                                           TUSB_CLASS_VENDOR_SPECIFIC,
                                           RESET_INTERFACE_SUBCLASS,
                                           RESET_INTERFACE_PROTOCOL,
                                           USBD_STR_RST_NAME,

#endif

// .------------------------------------------------------------------------.
// |    Support Generic USB Display (GUD)                                   |
// `------------------------------------------------------------------------'

#if CFG_TUD_GUD
    #error "No configuration descriptor implemented for 'CFG_TUD_GUD'"
#endif

// .------------------------------------------------------------------------.
// |    Support Vendor Commands (VENDOR)                                    |
// `------------------------------------------------------------------------'

#if CFG_TUD_VENDOR
    #error "No configuration descriptor implemented for 'CFG_TUD_VENDOR'"
#endif

};

// **************************************************************************
// *                                                                        *
// *    USB Device Callbacks                                                *
// *                                                                        *
// **************************************************************************

const uint8_t *tud_descriptor_device_cb(void) {
    return (const uint8_t *)&usbd_desc_device;
}

const uint8_t *tud_descriptor_configuration_cb(uint8_t __unused index) {
    return usbd_desc_cfg;
}

const uint16_t *tud_descriptor_string_cb(uint8_t index, uint16_t langid) {
    #define DESC_STR_MAX_LENGTH (20)
    static uint16_t desc_str[DESC_STR_MAX_LENGTH];

    uint8_t len;
    if (index == USBD_STR_LANGUAGE) {
        desc_str[1] = 0x0409; // Supported language is English
        len = 1;
    } else {
        if (index >= sizeof(usbd_desc_str) / sizeof(usbd_desc_str[0])) {
            return NULL;
        }
        if (index == USBD_STR_SERIAL_NUMBER) {
            pico_unique_board_id_t id;
            pico_get_unique_board_id(&id);
            // byte by byte conversion
            for (len = 0; len < 16; len += 2) {
                const char *hexdig = "0123456789ABCDEF";
                desc_str[1 + len + 0] = hexdig[id.id[len >> 1] >> 4];
                desc_str[1 + len + 1] = hexdig[id.id[len >> 1] & 0x0F];
            }
#if CFG_TUD_NET
        } else if (index == USBD_STR_NET_MAC_ADDR) {
            for (len = 0; len < sizeof(tud_network_mac_address); len+=2)
            {
                const char *hexdig = "0123456789ABCDEF";
                desc_str[1 + len + 0] = hexdig[tud_network_mac_address[len >> 1] >> 4];
                desc_str[1 + len + 1] = hexdig[tud_network_mac_address[len >> 1] & 0x0F];
            }
#endif
        } else {
            const char *str = usbd_desc_str[index];
            for (len = 0; len < DESC_STR_MAX_LENGTH - 1 && str[len]; ++len) {
                desc_str[1 + len] = str[len];
            }
        }
    }

    // first byte is length (including header), second byte is string type
    desc_str[0] = (TUSB_DESC_STRING << 8) | (2 * len + 2);

    return desc_str;
}

#if CFG_TUD_HID

const uint8_t *tud_hid_descriptor_report_cb(uint8_t instance) {
    return desc_hid_report;
}

#endif
