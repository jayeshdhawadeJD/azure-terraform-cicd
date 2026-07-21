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
  name                  = "demo-files"
  storage_account_name    = azurerm_storage_account.demo.name
  container_access_type = "private"
}
