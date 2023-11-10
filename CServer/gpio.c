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
int export_gpio(uint8_t pin) {
    // create pin string
    int already_exported = 0;
    char pin_string[2];
    char exported_string[6];
    sprintf(pin_string, "%u", pin);
    sprintf(exported_string, "gpio%u", pin);




    // check if pin has been exported
    struct dirent *de;  // Pointer for directory entry 
    // opendir() returns a pointer of DIR type.  
    DIR *dr = opendir("/sys/class/gpio/"); 
  
    if (dr == NULL)  // opendir returns NULL if couldn't open directory 
    { 
        printf("Could not open current directory" ); 
        return 0; 
    } 
  
    int result;
    while ((de = readdir(dr)) != NULL)  {
            result = strcmp(de->d_name, exported_string);
            if (result == 0) {
                already_exported = 1;
            }
    }
    closedir(dr);


    if (already_exported == 0) { // check if pin is already exported or not
        int fd_export = open("/sys/class/gpio/export", O_WRONLY);
        if (fd_export == -1) {
            perror("Failed to open /sys/class/gpio/export");

            return -1;
        }
        
        if (write(fd_export, pin_string, strlen(pin_string)) == -1) {
            perror("Failed to export GPIO pin");
            printf("failed pin: %s\n",pin_string);
            close(fd_export);
            return -1;
        }
        
        close(fd_export);
    }
    return 0;
    
  


  

}

// Function to set the direction of a GPIO pin to "out"
int set_gpio_direction_out(uint8_t pin) {

    char direction_path[128];
    snprintf(direction_path, sizeof(direction_path), "/sys/class/gpio/gpio%u/direction", pin);

    
    int fd_direction = open(direction_path, O_WRONLY);
    if (fd_direction == -1) {
        perror("Failed to open GPIO direction file");
        return -1;
    }
    
    if (write(fd_direction, "out", 3) == -1) {
        perror("Failed to set GPIO direction to 'out'");
        close(fd_direction);
        return -1;
    }
    
    close(fd_direction);

    
    return 0;
}

// Function to set the direction of a GPIO pin to "in"
int set_gpio_direction_in(uint8_t pin) {

    char direction_path[128];
    snprintf(direction_path, sizeof(direction_path), "/sys/class/gpio/gpio%u/direction", pin);


    int fd_direction = open(direction_path, O_WRONLY);
    if (fd_direction == -1) {
        perror("Failed to open GPIO direction file");
        return -1;
    }
    
    if (write(fd_direction, "in", 3) == -1) {
        perror("Failed to set GPIO direction to 'in'");
        close(fd_direction);
        return -1;
    }
    
    close(fd_direction);

    
    return 0;
}

// Function to write a value (1 or 0) to a GPIO pin
int write_gpio_value(uint8_t pin, int value) {


    char value_path[128];
    snprintf(value_path, sizeof(value_path), "/sys/class/gpio/gpio%u/value", pin);

    int fd_value = open(value_path, O_WRONLY);
    if (fd_value == -1) {
        perror("Failed to open GPIO value file");
        return -1;
    }

    char buffer[2];
    snprintf(buffer, sizeof(buffer), "%d", value);

    
    if (write(fd_value, buffer, 1) == -1) {
        perror("Failed to write GPIO value");
        close(fd_value);
        return -1;
    }
    
    close(fd_value);


    return 0;
}