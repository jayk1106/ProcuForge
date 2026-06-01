export interface EstimatedPriceRange {
  currency: string
  min: number
  max: number
}

export interface ProductOption {
  id: string
  name: string
  brand: string
  description: string
  estimatedPriceRange: EstimatedPriceRange
}
