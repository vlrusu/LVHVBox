#ifndef RS485_NOTIFY_H
#define RS485_NOTIFY_H

/* Best-effort, nonblocking notification after all-channel LV power-on.
 * Returns 0 when sent/not applicable, -1 on delivery failure (errno set).
 * Never changes the power command's result or waits for discovery. */
int rs485_notify_power_on(unsigned int channel, int power_result);

#endif
