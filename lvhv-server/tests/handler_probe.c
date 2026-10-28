/* Run the real client handler with queue/log/Pico stubs. No hardware access. */
#include "handler.h"
#include <sys/socket.h>
static unsigned int dispatches;
void log_write(Logger_t *logger, char *text, unsigned int level) {
    (void)logger; (void)text; (void)level;
}
int pico_is_connected(size_t id) { (void)id; return 0; }
void queue_push(PriorityQueue_t *queue, QueueItem_t *item) {
    (void)queue;
    ++dispatches;
    task_t *task = item->payload;
    task->rv = message_wrap_int(0);
    task->complete = 1;
}
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    client_handler_args_t *args = calloc(1, sizeof *args);
    if (!args) return 3;
    args->client_addr = atoi(argv[1]);
    pthread_t thread;
    if (pthread_create(&thread, NULL, client_handler, args)) { free(args); return 4; }
    if (pthread_join(thread, NULL)) return 5;
    printf("%u\n", dispatches);
    return 0;
}
