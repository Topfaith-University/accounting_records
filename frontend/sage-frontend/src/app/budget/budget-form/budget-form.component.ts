import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, FormArray, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { BudgetService } from '../../services/budget.service';
import { AccountsService } from '../../services/accounts.service';
import { AccountSelectComponent } from '../../shared/account-select/account-select.component';

@Component({
  selector: 'app-budget-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, AccountSelectComponent],
  templateUrl: './budget-form.component.html',
})
export class BudgetFormComponent implements OnInit {
  form!: FormGroup;
  accounts: any[] = [];
  allAccounts: any[] = [];
  saving = false;
  error = '';

  get lines(): FormArray { return this.form.get('lines') as FormArray; }

  get total(): number {
    return this.lines.controls.reduce((sum, l) => sum + (Number(l.value.budgeted_amount) || 0), 0);
  }

  constructor(
    private fb: FormBuilder,
    private budgetService: BudgetService,
    private accountsService: AccountsService,
    private router: Router,
  ) {}

  async ngOnInit() {
    this.form = this.fb.group({
      name: ['', Validators.required],
      fiscal_year: ['', Validators.required],
      lines: this.fb.array([]),
    });
    this.addLine();
    try {
      const data = await this.accountsService.getAll();
      this.accounts = data.results ?? data;
      this.allAccounts = [...this.accounts];
    } catch {
      this.error = 'Failed to load accounts.';
    }
  }

  addLine() {
    this.lines.push(this.fb.group({
      account_id: ['', Validators.required],
      budgeted_amount: [null, [Validators.required, Validators.min(0.01)]],
    }));
  }

  removeLine(i: number) {
    if (this.lines.length > 1) this.lines.removeAt(i);
  }

  async save() {
    if (!this.form.valid || this.saving) return;
    this.saving = true;
    this.error = '';
    try {
      const budget = await this.budgetService.create(this.form.value);
      this.router.navigate(['/budget', budget.budget_id]);
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Save failed.');
    } finally {
      this.saving = false;
    }
  }
}
