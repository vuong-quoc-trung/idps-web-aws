#include <sys/socket.h>
#include <sys/xattr.h>
#include <netinet/in.h>
#include <unistd.h>
#include <errno.h>
#include <stdio.h>
int main(void){
 printf("{\"uid\":%u,\"gid\":%u",getuid(),getgid());
 int fd=socket(AF_INET,SOCK_DGRAM,IPPROTO_ICMP);int err=fd<0?errno:0;
 printf(",\"icmp_dgram_fd_ok\":%s,\"icmp_dgram_errno\":%d",fd>=0?"true":"false",err);if(fd>=0)close(fd);
 fd=socket(AF_INET,SOCK_RAW,IPPROTO_ICMP);err=fd<0?errno:0;
 printf(",\"icmp_raw_fd_ok\":%s,\"icmp_raw_errno\":%d",fd>=0?"true":"false",err);if(fd>=0)close(fd);
 unsigned char buf[64];ssize_t n=getxattr("/usr/bin/ping","security.capability",buf,sizeof(buf));
 int xe=n<0?errno:0;printf(",\"ping_capability_xattr_errno\":%d,\"ping_capability_xattr_length\":%zd,\"ping_capability_xattr_hex\":\"",xe,n);for(int i=0;i<n;i++)printf("%02x",buf[i]);puts("\"}");return 0;
}
