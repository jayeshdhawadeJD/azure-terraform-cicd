terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.110"
    }
  }

  backend "azurerm" {
    resource_group_name  = "rg-tfstate"
    storage_account_name = "tfstatejd2026"
    container_name        = "tfstate"
    key                    = "demo-infra.tfstate"
    use_oidc               = true
    use_azuread_auth        = true
  }
}

provider "azurerm" {
  features {}
  use_oidc = true
}

resource "azurerm_resource_group" "demo" {
  name     = "rg-portfolio-demo"
  location = "centralindia"
}

resource "azurerm_storage_account" "demo" {
  name                     = "stportfoliodemo01"  # must be globally unique - change if needed
  resource_group_name      = azurerm_resource_group.demo.name
  location                 = azurerm_resource_group.demo.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "demo" {
  name                  = "demo-list"
  storage_account_name    = azurerm_storage_account.demo.name
  container_access_type = "private"
}

resource "azurerm_container_app_environment" "demo" {
  name                = "cae-portfolio-demo"
  location            = azurerm_resource_group.demo.location
  resource_group_name = azurerm_resource_group.demo.name
}

resource "azurerm_container_app" "demo" {
  name                         = "ca-portfolio-flask"
  container_app_environment_id = azurerm_container_app_environment.demo.id
  resource_group_name          = azurerm_resource_group.demo.name
  revision_mode                = "Single"
   identity {
    type = "SystemAssigned"
  }
  template {
    container {
      name   = "flask-app"
      image  = "ghcr.io/jayeshdhawadejd/azure-terraform-cicd/portfolio-flask:latest"
      cpu    = 0.25
      memory = "0.5Gi"
    }
  }

  ingress {
    allow_insecure_connections = false
    external_enabled           = true
    target_port                = 5000
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
}

