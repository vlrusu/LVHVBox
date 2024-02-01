// C library headers
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#include <math.h>

// Linux headers
#include <fcntl.h> // Contains file controls like O_RDWR
#include <errno.h> // Error integer and strerror() function
#include <termios.h> // Contains POSIX terminal control definitions
#include <unistd.h> // write(), read(), close()

#include <time.h>
#include <dirent.h> 



#include <sys/mman.h>
#include <stdint.h>


typedef struct{
    uint32_t status;
    uint32_t ctrl; 
}GPIOregs;
#define GPIO ((GPIOregs*)GPIOBase)
typedef struct
{
    uint32_t Out;
    uint32_t OE;
    uint32_t In;
    uint32_t InSync;
} rioregs;
#define rio ((rioregs *)RIOBase)
#define rioXOR ((rioregs *)(RIOBase + 0x1000 / 4))
#define rioSET ((rioregs *)(RIOBase + 0x2000 / 4))
#define rioCLR ((rioregs *)(RIOBase + 0x3000 / 4))


int microsecond_sleep(long usec)
{
    struct timespec ts;
    int res;

    if (usec < 0)
    {
        errno = EINVAL;
        return -1;
    }

    ts.tv_sec = usec / 1000000;
    ts.tv_nsec = (usec % 1000000) * 1000;

    do {
        res = nanosleep(&ts, &ts);
    } while (res && errno == EINTR);

    return res;
}



// Function to export a GPIO pin
int setup_gpio(uint32_t pin) {
    int memfd = open("/dev/mem", O_RDWR | O_SYNC);
    uint32_t *map = (uint32_t *)mmap(
        NULL,
        64 * 1024 * 1024,
        (PROT_READ | PROT_WRITE),
        MAP_SHARED,
        memfd,
        0x1f00000000
    );
    if (map == MAP_FAILED)
    {
        printf("mmap failed: %s\n", strerror(errno));
        return (-1);
    };
    close(memfd);
    uint32_t *PERIBase = map;
    uint32_t *GPIOBase = PERIBase + 0xD0000 / 4;
    uint32_t *RIOBase = PERIBase + 0xe0000 / 4;
    uint32_t *PADBase = PERIBase + 0xf0000 / 4;
    uint32_t *pad = PADBase + 1;   
    uint32_t fn = 5;
    GPIO[pin].ctrl=fn;
    pad[pin] = 0x10;
    rioSET->OE = 0x01<<pin;


    return 0;
    
  

}





// Function to write a value (1 or 0) to a GPIO pin
int write_gpio_value(uint32_t pin, int value) {


    int memfd = open("/dev/mem", O_RDWR | O_SYNC);
    uint32_t *map = (uint32_t *)mmap(
        NULL,
        64 * 1024 * 1024,
        (PROT_READ | PROT_WRITE),
        MAP_SHARED,
        memfd,
        0x1f00000000
    );
    if (map == MAP_FAILED)
    {
        printf("mmap failed: %s\n", strerror(errno));
        return (-1);
    };
    close(memfd);
    uint32_t *PERIBase = map;
    uint32_t *GPIOBase = PERIBase + 0xD0000 / 4;
    uint32_t *RIOBase = PERIBase + 0xe0000 / 4;
    uint32_t *PADBase = PERIBase + 0xf0000 / 4;
    uint32_t *pad = PADBase + 1;   
    uint32_t fn = 5;
    GPIO[pin].ctrl=fn;
    pad[pin] = 0x10;


    if (value == 0) {
        rioCLR->Out = 0x01<<pin;
    } else {
        rioSET->Out = 0x01<<pin;
    }


    return 0;
}