import "dotenv/config"
import mongoose from "mongoose"
import bcrypt from "bcryptjs"
import { User } from "@/db/models/User"

const BASE_URI = process.env.BASE_URI!

async function seedPLATFORM_OWNER() {
  await mongoose.connect(BASE_URI)

  const existing = await User.findOne({
    role: "PLATFORM_OWNER",
  })

  if (existing) {
    console.log("✅ PLATFORM_OWNER already exists")
    process.exit()
  }

  const hashedPassword = await bcrypt.hash("PLATFORM_OWNER123", 10)

  await User.create({
    email: "[EMAIL_ADDRESS]",
    password: hashedPassword,
    role: "PLATFORM_OWNER",
    name: "PLATFORM_OWNER User",
    phone: "1234567890",
    tenantId: null,
    twoFactorEnabled: false,
    notificationsEnabled: true,
  })

  console.log("🔥 PLATFORM_OWNER created successfully")
  process.exit()
}

seedPLATFORM_OWNER()
