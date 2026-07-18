package database

import (
	"fmt"
	"log"
	"voice2claim/backend/configs"
	"voice2claim/backend/internal/models"

	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

var DB *gorm.DB

func Connect(cfg *configs.Config) *gorm.DB {
	dsn := fmt.Sprintf("host=%s user=%s password=%s dbname=%s port=%s sslmode=disable TimeZone=Asia/Ho_Chi_Minh",
		cfg.DBHost, cfg.DBUser, cfg.DBPass, cfg.DBName, cfg.DBPort)

	db, err := gorm.Open(postgres.Open(dsn), &gorm.Config{})
	if err != nil {
		log.Fatalf("❌ Failed to connect to DB: %v", err)
	}
	log.Printf("✅ Connected to %s successfully", cfg.DBName)

	// ⚠️ QUAN TRỌNG: Tự động tạo/cập nhật bảng trong DB
	err = db.AutoMigrate(
		&models.ClaimType{},
		&models.User{},
		&models.Claim{},
		&models.ClaimEntity{},
		&models.ClaimVehicle{},
		&models.ClaimMedical{},
	)
	if err != nil {
		log.Fatalf("❌ Failed to migrate database: %v", err)
	}
	log.Println("✅ Database tables migrated successfully")

	DB = db
	return db
}