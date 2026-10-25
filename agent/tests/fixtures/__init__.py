"""
Shared Test Fixtures and Sample Data for AutoFix Agent Tests.
"""
from __future__ import annotations

from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent
SAMPLE_REPO_DIR = FIXTURES_DIR / "sample_repo"

PYTHON_TRACEBACK_SAMPLE = """
Traceback (most recent call last):
  File "/workspace/src/app.py", line 12, in <module>
    run_server()
  File "/workspace/src/payment/processor.py", line 45, in calculate_fee
    fee = amount * rate
TypeError: unsupported operand type(s) for *: 'NoneType' and 'float'
"""

JS_STACK_TRACE_SAMPLE = """
TypeError: Cannot read properties of undefined (reading 'rate')
    at calculateTax (services/taxCalculator.ts:24:18)
    at processPayment (controllers/paymentController.ts:60:12)
    at Layer.handle [as handle_request] (/node_modules/express/lib/router/layer.js:95:5)
"""

GENERIC_COMPILER_ERROR_SAMPLE = """
src/models/user.py:58:12: error: Name 'hashed_pw' is used before definition
FAILED tests/test_auth.py::test_login - AssertionError: assert False
"""

GITHUB_ISSUE_SAMPLE = """
Bug Report: Payment calculation failed with TypeError in checkout

When a user attempts checkout with a discount voucher, the application crashes:

```
TypeError: Cannot read properties of undefined (reading 'rate')
    at calculateTax (services/taxCalculator.ts:24:18)
    at processPayment (controllers/paymentController.ts:60:12)
```

The `taxCalculator` is throwing an error when tax exemption is enabled.
Please check `services/taxCalculator.ts` and function `calculateTax`.
"""

NATURAL_LANGUAGE_ISSUE_SAMPLE = """
Feature Broken: Checkout button does not respond on mobile devices.
When the user clicks the 'Confirm Purchase' button on iOS Safari, nothing happens.
There are no console errors shown. Check `CheckoutButton.tsx` and `handleCheckout`.
"""

PYTHON_SOURCE_SAMPLE = """# Payment Processor Module

class PaymentProcessor:
    def __init__(self, currency: str = "USD"):
        self.currency = currency

    def calculate_fee(self, amount: float, rate: float | None) -> float:
        \"\"\"Calculate processing fee.\"\"\"
        if rate is None:
            raise ValueError("Rate must not be None")
        return amount * rate

def format_currency(amount: float, symbol: str = "$") -> str:
    return f"{symbol}{amount:.2f}"
"""

TYPESCRIPT_SOURCE_SAMPLE = """// Tax Calculator Service

export interface TaxConfig {
  defaultRate: number;
  exemptRegions: string[];
}

export function calculateTax(amount: number, config?: TaxConfig): number {
  if (!config) {
    throw new TypeError("Cannot read properties of undefined (reading 'rate')");
  }
  return amount * config.defaultRate;
}

export class TaxManager {
  private config: TaxConfig;

  constructor(config: TaxConfig) {
    this.config = config;
  }

  public getRate(): number {
    return this.config.defaultRate;
  }
}
"""

GO_SOURCE_SAMPLE = """package payment

import "fmt"

// CalculateFee computes transaction fee.
func CalculateFee(amount float64, rate *float64) (float64, error) {
    if rate == nil {
        return 0, fmt.Errorf("rate cannot be nil")
    }
    return amount * (*rate), nil
}

type PaymentGateway struct {
    APIKey string
}

func (p *PaymentGateway) Process(amount float64) bool {
    return true
}
"""

JAVA_SOURCE_SAMPLE = """package com.example.payment;

/**
 * Payment processor service.
 */
public class PaymentProcessor {
    private double defaultRate;

    public PaymentProcessor(double defaultRate) {
        this.defaultRate = defaultRate;
    }

    /**
     * Calculates transaction fee.
     */
    public double calculateFee(double amount, Double rate) {
        if (rate == null) {
            throw new IllegalArgumentException("rate cannot be null");
        }
        return amount * rate;
    }
}
"""

GO_PANIC_SAMPLE = """
panic: runtime error: invalid memory address or nil pointer dereference
[signal SIGSEGV: segmentation violation code=0x1 addr=0x0 pc=0x10a4e80]

goroutine 1 [running]:
main.CalculateFee(0x408f400000000000, 0x0)
\t/workspace/payment/processor.go:45 +0x24
main.main()
\t/workspace/main.go:12 +0x30
"""

JAVA_EXCEPTION_SAMPLE = """
java.lang.NullPointerException: Cannot invoke "java.lang.Double.doubleValue()" because "rate" is null
\tat com.example.payment.PaymentProcessor.calculateFee(PaymentProcessor.java:45)
\tat com.example.payment.Application.main(Application.java:12)
"""
