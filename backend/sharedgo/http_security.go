// shared/http_security.go
package shared

import (
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

// Danh sách allowed hosts
var allowedHosts map[string]bool

// LoadAllowedHosts khởi tạo danh sách host được phép từ config + env CORS
func LoadAllowedHosts() {
	cfg := GlobalConfig.Get()
	allowedHosts = make(map[string]bool)

	// 1. Production domains (hardcode)
	allowedHosts["dathoc.net"] = true
	allowedHosts["www.dathoc.net"] = true

	// 2. ✅ Parse CORS từ env: "http://localhost:8074,http://192.168.0.101:8074,https://dathoc.net"
	corsRaw := getEnv("CORS", "")
	if corsRaw != "" {
		for _, origin := range strings.Split(corsRaw, ",") {
			origin = strings.TrimSpace(origin)
			if origin == "" {
				continue
			}
			// Parse URL để lấy host
			u, err := url.Parse(origin)
			if err != nil {
				// Nếu không parse được, thử dùng trực tiếp làm host
				host := NormalizeHost(origin)
				allowedHosts[host] = true
				continue
			}
			// Chuẩn hóa host (loại bỏ port mặc định 80/443)
			host := NormalizeHost(u.Host)
			allowedHosts[host] = true
		}
	}

	// 3. Development environments (chỉ thêm nếu không phải production)
	if cfg.ServiceName != "production" {
		// Thêm localhost với các port thường dùng trong dev
		allowedHosts["localhost:8074"] = true
		allowedHosts["localhost:8075"] = true
		allowedHosts["127.0.0.1:8074"] = true
		allowedHosts["127.0.0.1:8075"] = true
		allowedHosts["localhost"] = true
		allowedHosts["127.0.0.1"] = true

		// Có thể thêm từ config DEV_HOSTS
		if devHosts := getEnv("DEV_HOSTS", ""); devHosts != "" {
			for _, host := range strings.Split(devHosts, ",") {
				host = strings.TrimSpace(host)
				if host != "" {
					allowedHosts[NormalizeHost(host)] = true
				}
			}
		}
	}

	// Log debug để kiểm tra danh sách allowed hosts
	if Logger != nil {
		var hosts []string
		for h := range allowedHosts {
			hosts = append(hosts, h)
		}
		Logger.Debug("Allowed hosts loaded", "count", len(hosts), "hosts", hosts)
	}
}

var (
	// Global variables để cache kết quả
	cloudflareIPv4CIDRs  []string
	cloudflareIPv6CIDRs  []string
	lastCloudflareUpdate time.Time
	cloudflareMu         sync.RWMutex
)

func init() {
	if GlobalConfig.Get().ServiceName == "production" {
		// Giá trị mặc định nếu không tải được từ internet
		cloudflareIPv4CIDRs = []string{
			"173.245.48.0/20",
			"103.21.244.0/22",
			"103.22.200.0/22",
			"103.31.4.0/22",
			"141.101.64.0/18",
			"108.162.192.0/18",
			"190.93.240.0/20",
			"188.114.96.0/20",
			"197.234.240.0/22",
			"198.41.128.0/17",
			"162.158.0.0/15",
			"104.16.0.0/13",
			"104.24.0.0/14",
			"172.64.0.0/13",
			"131.0.72.0/22",
		}
		cloudflareIPv6CIDRs = []string{
			"2400:cb00::/32",
			"2606:4700::/32",
			"2803:f800::/32",
			"2405:b500::/32",
			"2405:8100::/32",
			"2a06:98c0::/29",
			"2c0f:f248::/32",
		}
		lastCloudflareUpdate = time.Now()

		// Chạy async để cập nhật mới
		go func() {
			updateCloudflareIPs()
			Logger.Info("Cloudflare IPs updated in background")
		}()
	} else {
		// Dev environment
		cloudflareIPv4CIDRs = []string{"172.16.0.0/12", "192.168.0.0/16", "10.0.0.0/8"}
		cloudflareIPv6CIDRs = []string{"fd00::/8"}
	}
}

// getTrustedCDNIPs trả về danh sách CIDR của các CDN được trust
func getTrustedCDNIPs() []string {
	cfg := GlobalConfig.Get()

	// 1. Production environment
	if cfg.ServiceName == "production" {
		return getProductionTrustedCDNs()
	}

	// 2. Development/Staging
	return getDevTrustedNetworks()
}

// getProductionTrustedCDNs lấy CIDR từ CDN thực tế (Cloudflare ví dụ)

func getProductionTrustedCDNs() []string {
	cloudflareMu.RLock()
	defer cloudflareMu.RUnlock()

	trusted := append([]string{}, cloudflareIPv4CIDRs...)
	trusted = append(trusted, cloudflareIPv6CIDRs...)

	if useAWS() {
		trusted = append(trusted, getAWSGlobalAcceleratorCIDRs()...)
	}

	return trusted
}

// updateCloudflareIPs cập nhật IP ranges từ Cloudflare API
/*
func getProductionTrustedCDNs() []string {
	// Tự động cập nhật mỗi 24h
	if time.Since(lastCloudflareUpdate) > 24*time.Hour {
		updateCloudflareIPs()
	}

	// Gom cả IPv4 và IPv6
	trusted := make([]string, 0, len(cloudflareIPv4CIDRs)+len(cloudflareIPv6CIDRs))
	trusted = append(trusted, cloudflareIPv4CIDRs...)
	trusted = append(trusted, cloudflareIPv6CIDRs...)

	// Thêm AWS ALB nếu cần
	if useAWS() {
		trusted = append(trusted, getAWSGlobalAcceleratorCIDRs()...)
	}

	return trusted
}
func updateCloudflareIPs() {
	if !isInternetAvailable() {
        Logger.Warn("No internet connection, skip Cloudflare IP update")
        return
    }
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// 1. Thử cập nhật IPv4
    if ipv4s, err := fetchCloudflareIPs(ctx, "https://www.cloudflare.com/ips-v4"); err != nil {
        Logger.Warn("Failed to fetch Cloudflare IPv4 ranges", "error", err)
    } else {
        cloudflareIPv4CIDRs = ipv4s
        Logger.Info("Updated Cloudflare IPv4 ranges", "count", len(ipv4s))
    }

    // 2. Thử cập nhật IPv6 (không phụ thuộc IPv4)
    if ipv6s, err := fetchCloudflareIPs(ctx, "https://www.cloudflare.com/ips-v6"); err != nil {
        Logger.Warn("Failed to fetch Cloudflare IPv6 ranges", "error", err)
    } else {
        cloudflareIPv6CIDRs = ipv6s
        Logger.Info("Updated Cloudflare IPv6 ranges", "count", len(ipv6s))
    }

    lastCloudflareUpdate = time.Now()
}
*/
func updateCloudflareIPs() {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if ipv4s, err := fetchCloudflareIPs(ctx, "https://www.cloudflare.com/ips-v4"); err == nil {
		cloudflareMu.Lock()
		cloudflareIPv4CIDRs = ipv4s
		lastCloudflareUpdate = time.Now()
		cloudflareMu.Unlock()
	}

	if ipv6s, err := fetchCloudflareIPs(ctx, "https://www.cloudflare.com/ips-v6"); err == nil {
		cloudflareMu.Lock()
		cloudflareIPv6CIDRs = ipv6s
		lastCloudflareUpdate = time.Now()
		cloudflareMu.Unlock()
	}
}

// fetchCloudflareIPs lấy CIDR từ URL của Cloudflare
func fetchCloudflareIPs(ctx context.Context, url string) ([]string, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return nil, err
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	// Parse kết quả (mỗi dòng là 1 CIDR)
	var cidrs []string
	for _, line := range strings.Split(string(body), "\n") {
		cidr := strings.TrimSpace(line)
		if cidr != "" && !strings.HasPrefix(cidr, "#") {
			cidrs = append(cidrs, cidr)
		}
	}

	return cidrs, nil
}

// getDevTrustedNetworks cho môi trường dev/staging
func getDevTrustedNetworks() []string {
	return []string{
		"127.0.0.0/8",    // Localhost
		"10.0.0.0/8",     // Private network
		"172.16.0.0/12",  // Docker networks
		"192.168.0.0/16", // Private network
		"fd00::/8",       // Private IPv6
		"::1/128",        // IPv6 localhost
	}
}

// getAWSGlobalAcceleratorCIDRs (nếu dùng AWS)
func getAWSGlobalAcceleratorCIDRs() []string {
	// Lấy từ https://ip-ranges.amazonaws.com/ip-ranges.json
	// Chỉ lấy các CIDR chứa "service": "GLOBALACCELERATOR"
	return []string{
		"13.248.118.0/24",
		"15.164.160.0/22",
		// ... thêm các CIDR thực tế
	}
}

// useAWS kiểm tra có dùng dịch vụ AWS không
func useAWS() bool {
	v := strings.ToLower(getEnv("CLOUD_PROVIDER", ""))
	return strings.Contains(v, "aws")
}

// NormalizeHost xử lý host string về dạng chuẩn
func NormalizeHost(host string) string {
	host = strings.ToLower(host)
	// Loại bỏ port mặc định
	if strings.HasSuffix(host, ":80") {
		return strings.TrimSuffix(host, ":80")
	}
	if strings.HasSuffix(host, ":443") {
		return strings.TrimSuffix(host, ":443")
	}
	return host
}

// GetEffectiveOrigin lấy origin thực tế từ request
func GetEffectiveOrigin(r *http.Request) string {
	// Ưu tiên header từ reverse proxy
	if fwd := r.Header.Get("X-Forwarded-Origin"); fwd != "" {
		return fwd
	}
	return r.Header.Get("Origin")
}

// GetEffectiveReferer lấy referer thực tế từ request
func GetEffectiveReferer(r *http.Request) string {
	// Ưu tiên header từ reverse proxy
	if fwd := r.Header.Get("X-Forwarded-Referer"); fwd != "" {
		return fwd
	}
	return r.Header.Get("Referer")
}

// IsValidOrigin kiểm tra origin có hợp lệ không
func IsValidOrigin(origin string) bool {
	if origin == "" {
		return false
	}

	u, err := url.Parse(origin)
	if err != nil {
		return false
	}

	host := NormalizeHost(u.Host)
	_, ok := allowedHosts[host]
	return ok
}

// IsValidReferer kiểm tra referer có hợp lệ không
func IsValidReferer(referer string) bool {
	if referer == "" {
		return false
	}

	u, err := url.Parse(referer)
	if err != nil {
		return false
	}

	host := NormalizeHost(u.Host)
	_, ok := allowedHosts[host]
	return ok
}

// IsTrustedIP kiểm tra IP có đáng tin cậy không
/*
func IsTrustedIP(ip string) bool {
	// Trong production, nên lấy từ config hoặc database
	trustedNetworks := []string{"127.0.0.1", "localhost", "10.", "192.168.", "172.16.", "172.31."}

	for _, network := range trustedNetworks {
		if strings.HasPrefix(ip, network) {
			return true
		}
	}

	// Thêm các IP trusted từ config
	if trustedIPs := getEnv("TRUSTED_IPS", ""); trustedIPs != "" {
		for _, trustedIP := range strings.Split(trustedIPs, ",") {
			if strings.TrimSpace(trustedIP) == ip {
				return true
			}
		}
	}

	return false
}
*/
func IsTrustedIP(ip string) bool {
	// 1. Trust localhost
	if ip == "127.0.0.1" || ip == "::1" || ip == "localhost" {
		return true
	}

	// 2. Trust private networks (RFC 1918) bằng CIDR chính xác
	privateCIDRs := []string{
		//"10.0.0.0/8",       // Toàn bộ 10.0.0.0 → 10.255.255.255
		//"192.168.0.0/16",   // Toàn bộ 192.168.0.0 → 192.168.255.255
		"172.16.0.0/12", // Toàn bộ 172.16.0.0 → 172.31.255.255 (16 → 31)
		//"172.31.0.0/12",
	}

	for _, cidr := range privateCIDRs {
		if isIPInCIDR(ip, cidr) {
			return true
		}
	}

	// 3. Trust IPs từ env
	if trustedIPs := getEnv("TRUSTED_IPS", ""); trustedIPs != "" {
		for _, trustedIP := range strings.Split(trustedIPs, ",") {
			if strings.TrimSpace(trustedIP) == ip {
				return true
			}
		}
	}

	return false
}
func isIPInCIDR(ipStr, cidr string) bool {
	// 1. Chuẩn hóa IP (loại bỏ port nếu có)
	ipStr = strings.Split(ipStr, ":")[0] // Xử lý trường hợp "192.168.1.1:12345"

	// 2. Parse IP và CIDR
	ip := net.ParseIP(ipStr)
	if ip == nil {
		return false // IP không hợp lệ
	}

	_, ipNet, err := net.ParseCIDR(cidr)
	if err != nil {
		return false // CIDR không hợp lệ
	}

	// 3. Xử lý IPv4-mapped IPv6 (vd: ::ffff:192.168.1.1)
	if ipv4 := ip.To4(); ipv4 != nil {
		ip = ipv4 // Chuyển về IPv4 thuần để so sánh
	}

	// 4. Kiểm tra IP có trong network không
	return ipNet.Contains(ip)
}
func IsTrustedProxy(ip string) bool {
	// 1. Trusted CDN IPs (Cloudflare, AWS...)
	trustedCDNs := getTrustedCDNIPs() // Hàm trả về []string

	for _, cidr := range trustedCDNs {
		if isIPInCIDR(ip, cidr) { // Hàm kiểm tra IP trong CIDR
			return true
		}
	}

	// 2. Trusted internal proxies (Nginx trong VPC)
	if GlobalConfig.Get().ServiceName == "production" {
		return ip == "10.0.0.100" // IP của Nginx trong VPC
	}

	// 3. Dev environment
	return strings.HasPrefix(ip, "172.17.") || // Docker
		strings.HasPrefix(ip, "172.18.") ||
		ip == "127.0.0.1"
}
func isInternetAvailable() bool {
	/*
	   ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	   defer cancel()
	   _, err := net.DialContext(ctx, "tcp", "8.8.8.8:53")
	   return err == nil
	*/
	return true
}
func RealIPMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		proxyIP := getIPFromRemoteAddr(r.RemoteAddr)

		if !IsTrustedProxy(proxyIP) {
			// Log cảnh báo nếu production
			if GlobalConfig.Get().ServiceName == "production" {
				Logger.Warn("Untrusted proxy detected", "proxy_ip", proxyIP)
			}
			next.ServeHTTP(w, r)
			return
		}

		if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
			// Lấy IP đầu tiên (client thực) và loại bỏ khoảng trắng
			clientIP := strings.TrimSpace(strings.Split(xff, ",")[0])

			// Validate IP format
			if parsedIP := net.ParseIP(clientIP); parsedIP != nil {
				// Chặn private IPs từ client thực
				if !isPrivateIP(parsedIP.String()) {
					r.RemoteAddr = clientIP + ":0"
					Logger.Debug("Real client IP set", "client_ip", clientIP, "proxy_ip", proxyIP)
				} else {
					Logger.Warn("Blocked private IP in X-Forwarded-For", "ip", clientIP)
				}
			}
		}

		next.ServeHTTP(w, r)
	})
}

// Helper: Kiểm tra IP có phải private không
func isPrivateIP(ip string) bool {
	privateCIDRs := []string{"10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "fd00::/8", "::1/128"}
	for _, cidr := range privateCIDRs {
		if isIPInCIDR(ip, cidr) {
			return true
		}
	}
	return false
}

// Helper: Trích xuất IP từ r.RemoteAddr
func getIPFromRemoteAddr(addr string) string {
	ip, _, _ := net.SplitHostPort(addr)
	return ip
}
