#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <time.h>
#include <pcap.h>

#define PORT 12345
#define BUF_SIZE 4096
#define RATE_LIMIT 100
#define RATE_LIMIT_PERIOD 1
#define BLOCK_DURATION 600

typedef struct {
    char ip[INET_ADDRSTRLEN];
    time_t timestamps[RATE_LIMIT];
    int count;
    time_t blocked_until;
} IPTracker;

IPTracker ip_tracker[1000];
int tracker_count = 0;

int find_ip_tracker(const char *ip) {
    for (int i = 0; i < tracker_count; i++) {
        if (strcmp(ip_tracker[i].ip, ip) == 0) {
            return i;
        }
    }
    return -1;
}

int is_valid_packet(const unsigned char *packet, int size) {
    struct iphdr *iph = (struct iphdr *)(packet + 14);  // Ethernet header size is 14 bytes
    if (iph->protocol == IPPROTO_UDP) {
        struct udphdr *udph = (struct udphdr *)(packet + 14 + iph->ihl * 4);
        if (ntohs(udph->dest) == PORT) {
            return 1;
        }
    }
    return 0;
}

int rate_limit(const char *ip) {
    time_t current_time = time(NULL);
    int idx = find_ip_tracker(ip);

    if (idx == -1) {
        strcpy(ip_tracker[tracker_count].ip, ip);
        ip_tracker[tracker_count].count = 0;
        ip_tracker[tracker_count].blocked_until = 0;
        idx = tracker_count;
        tracker_count++;
    }

    if (current_time < ip_tracker[idx].blocked_until) {
        return 0;
    }

    if (ip_tracker[idx].count < RATE_LIMIT) {
        ip_tracker[idx].timestamps[ip_tracker[idx].count] = current_time;
        ip_tracker[idx].count++;
    } else {
        for (int i = 1; i < RATE_LIMIT; i++) {
            ip_tracker[idx].timestamps[i - 1] = ip_tracker[idx].timestamps[i];
        }
        ip_tracker[idx].timestamps[RATE_LIMIT - 1] = current_time;

        if (current_time - ip_tracker[idx].timestamps[0] < RATE_LIMIT_PERIOD) {
            ip_tracker[idx].blocked_until = current_time + BLOCK_DURATION;
            ip_tracker[idx].count = 0;
            return 0;
        }
    }

    return 1;
}

void process_packet(const unsigned char *packet, int size, const char *source_ip) {
    if (is_valid_packet(packet, size) && rate_limit(source_ip)) {
        printf("Received valid packet from %s\n", source_ip);
        // Process the packet (game server logic here)
    } else {
        printf("Blocked packet from %s\n", source_ip);
    }
}

int main() {
    int sockfd;
    struct sockaddr_in server_addr, client_addr;
    unsigned char buffer[BUF_SIZE];
    socklen_t addr_len = sizeof(client_addr);
    char source_ip[INET_ADDRSTRLEN];

    if ((sockfd = socket(AF_INET, SOCK_DGRAM, 0)) < 0) {
        perror("Socket creation failed");
        exit(EXIT_FAILURE);
    }

    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(PORT);

    if (bind(sockfd, (const struct sockaddr *)&server_addr, sizeof(server_addr)) < 0) {
        perror("Bind failed");
        close(sockfd);
        exit(EXIT_FAILURE);
    }

    printf("Listening for UDP packets on port %d\n", PORT);

    while (1) {
        int n = recvfrom(sockfd, buffer, BUF_SIZE, 0, (struct sockaddr *)&client_addr, &addr_len);
        if (n < 0) {
            perror("Receive failed");
            continue;
        }

        inet_ntop(AF_INET, &(client_addr.sin_addr), source_ip, INET_ADDRSTRLEN);
        process_packet(buffer, n, source_ip);
    }

    close(sockfd);
    return 0;
}