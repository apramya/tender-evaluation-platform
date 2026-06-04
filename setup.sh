#!/bin/bash

# Tender Evaluation Platform - Setup Script
# This script sets up the development environment

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Tender Evaluation Platform - Setup Script            ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"

# Check prerequisites
echo -e "\n${BLUE}[1/5] Checking prerequisites...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}Docker not found. Please install Docker.${NC}"
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo -e "${YELLOW}Docker Compose v2 not found. Please install/update Docker Desktop.${NC}"
    exit 1
fi

if ! command -v git &> /dev/null; then
    echo -e "${YELLOW}Git not found. Please install Git.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ All prerequisites installed${NC}"

# Create environment file
echo -e "\n${BLUE}[2/5] Setting up environment...${NC}"

if [ ! -f .env ]; then
    echo -e "${YELLOW}Creating .env file from template...${NC}"
    cp .env.example .env
    
    # Generate secure JWT secret
    JWT_SECRET=$(openssl rand -hex 32)
    sed -i "s/your-super-secret-key-change-in-production-12345678/$JWT_SECRET/g" .env
    
    echo -e "${GREEN}✓ .env file created${NC}"
    echo -e "${YELLOW}Please edit .env and add GROQ_API_KEY plus S3 bucket/credentials before upload and AI testing.${NC}"
else
    echo -e "${GREEN}✓ .env file already exists${NC}"
fi

# Create necessary directories
echo -e "\n${BLUE}[3/5] Creating directories...${NC}"

mkdir -p uploads logs temp chroma_db
mkdir -p backend/tests
mkdir -p frontend/public/static

echo -e "${GREEN}✓ Directories created${NC}"

# Build and start services
echo -e "\n${BLUE}[4/5] Building Docker images...${NC}"

docker compose build --no-cache

echo -e "${GREEN}✓ Docker images built${NC}"

# Start services
echo -e "\n${BLUE}[5/5] Starting services...${NC}"

docker compose up -d

echo -e "${GREEN}✓ Services started${NC}"

# Wait for services to be ready
echo -e "\n${BLUE}Waiting for services to be ready...${NC}"

max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if curl -f http://localhost:8000/api/health &> /dev/null; then
        echo -e "${GREEN}✓ Backend is ready${NC}"
        break
    fi
    
    attempt=$((attempt + 1))
    sleep 1
done

if [ $attempt -eq $max_attempts ]; then
        echo -e "${YELLOW}Backend might not be ready. Check logs with: docker compose logs backend${NC}"
fi

# Seed database
echo -e "\n${BLUE}Initializing database...${NC}"

docker compose exec -T backend python -m scripts.seed_data || \
    echo -e "${YELLOW}Note: Database seeding failed. You can run it manually later.${NC}"

# Print summary
echo -e "\n${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║              Setup Complete!                           ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"

echo -e "\n${GREEN}Services are running:${NC}"
echo -e "  Frontend:   ${BLUE}http://localhost:3000${NC}"
echo -e "  Backend:    ${BLUE}http://localhost:8000${NC}"
echo -e "  API Docs:   ${BLUE}http://localhost:8000/docs${NC}"
echo -e "  Database:   ${BLUE}localhost:5432${NC}"
echo -e "  Redis:      ${BLUE}localhost:6379${NC}"

echo -e "\n${GREEN}Demo Credentials:${NC}"
echo -e "  Admin:      admin@tenderevaluation.com / admin123"
echo -e "  Officer:    officer@tenderevaluation.com / officer123"
echo -e "  User:       user@tenderevaluation.com / user12345"

echo -e "\n${GREEN}Next Steps:${NC}"
echo -e "  1. Open http://localhost:3000 in your browser"
echo -e "  2. Login with one of the demo credentials above"
echo -e "  3. Start exploring the platform!"

echo -e "\n${GREEN}Useful Commands:${NC}"
echo -e "  View logs:        docker compose logs -f backend"
echo -e "  Stop services:    docker compose down"
echo -e "  Restart services: docker compose restart"
echo -e "  Run tests:        docker compose exec backend pytest tests/"

echo -e "\n${YELLOW}Documentation:${NC}"
echo -e "  README:              ${BLUE}./README.md${NC}"
echo -e "  API Documentation:   ${BLUE}./API_DOCUMENTATION.md${NC}"
echo -e "  Deployment Guide:    ${BLUE}./DEPLOYMENT.md${NC}"

echo ""
