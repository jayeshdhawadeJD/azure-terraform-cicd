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

variable "image_tag" {
  description = "Container image tag to deploy"
  type        = string
  default     = "latest"
}

# NOTE: sensitive = true only hides the value from console/plan output.
# The PIN still lands in PLAINTEXT in the tfstate file (stored in the private
# tfstatejd2026 blob container, access-gated via RBAC). This is the first
# application-level secret going into state; keep the state container locked
# down as it already is.
variable "dashboard_pin" {
  description = "PIN required to trigger stop/start actions from the dashboard"
  type        = string
  sensitive   = true
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

  secret {
    name  = "dashboard-pin"
    value = var.dashboard_pin
  }

  identity {
    type = "SystemAssigned"
  }

  template {
    container {
      name   = "flask-app"
      image  = "ghcr.io/jayeshdhawadejd/azure-terraform-cicd/portfolio-flask:${var.image_tag}"
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name        = "APP_PIN"
        secret_name = "dashboard-pin"
      }
    }

min_replicas = 1
    max_replicas = 10
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

