import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { ReceivablesService } from '../../services/receivables.service';

@Component({
  selector: 'app-customer-list',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './customer-list.component.html',
})
export class CustomerListComponent implements OnInit {
  customers: any[] = [];
  loading = true;
  error = '';
  showForm = false;
  saving = false;
  formError = '';
  form!: FormGroup;

  constructor(private receivables: ReceivablesService, private fb: FormBuilder) {}

  async ngOnInit() {
    this.form = this.fb.group({
      name: ['', Validators.required],
      customer_type: ['EXTERNAL'],
      email: [''],
      phone: [''],
      address: [''],
    });
    await this.load();
  }

  async load() {
    this.loading = true;
    try {
      const data = await this.receivables.getCustomers();
      this.customers = data.results ?? data;
    } catch { this.error = 'Failed to load customers.'; }
    finally { this.loading = false; }
  }

  async submit() {
    if (!this.form.valid) return;
    this.saving = true;
    this.formError = '';
    try {
      await this.receivables.createCustomer(this.form.value);
      this.form.reset({ customer_type: 'EXTERNAL' });
      this.showForm = false;
      await this.load();
    } catch (e: any) {
      this.formError = e.response?.data?.detail ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Save failed.');
    } finally { this.saving = false; }
  }
}
