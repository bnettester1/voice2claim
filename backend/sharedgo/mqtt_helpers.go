package shared

import (
	"fmt"
)

// PublishPresence cập nhật trạng thái online/offline (retain=true để client mới join thấy ngay)
func PublishPresence(clientID, status string) {
	if MQTT == nil || !MQTT.IsConnected() {
		return
	}
	topic := fmt.Sprintf("presence/%s/%s", GlobalConfig.Get().ServiceName, clientID)
	MQTT.Publish(topic, 1, true, []byte(status))
}

// PushNotification gửi alert/notification low-bandwidth
func PushNotification(targetUser, title, body string) {
	if MQTT == nil || !MQTT.IsConnected() {
		return
	}
	topic := fmt.Sprintf("push/%s", targetUser)
	payload := fmt.Sprintf(`{"title":"%s","body":"%s","ts":"%s"}`, title, body, GlobalConfig.Get().ServiceName)
	MQTT.Publish(topic, 1, false, []byte(payload))
}
