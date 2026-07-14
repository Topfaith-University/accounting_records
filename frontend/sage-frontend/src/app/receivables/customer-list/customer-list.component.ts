import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { ReceivablesService } from '../../services/receivables.service';
import { PaginatePipe } from '../../shared/paginate.pipe';
import { PaginationComponent } from '../../shared/pagination/pagination.component';

@Component({
  selector: 'app-customer-list',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, PaginatePipe, PaginationComponent],
  templateUrl: './customer-list.component.html',
})
export class CustomerListComponent implements OnInit {
  customers: any[] = [];
  loading = true;
  error = '';
  page = 1;
  pageSize = 25;
  showForm = false;
  saving = false;
  formError = '';
  form!: FormGroup;
  editingCustomerId: string | null = null;

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
      if (this.editingCustomerId) {
        await this.receivables.updateCustomer(this.editingCustomerId, this.form.value);
      } else {
        await this.receivables.createCustomer(this.form.value);
      }
      this.form.reset({ customer_type: 'EXTERNAL' });
      this.editingCustomerId = null;
      this.showForm = false;
      await this.load();
    } catch (e: any) {
      this.formError = e.response?.data?.detail ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Save failed.');
    } finally { this.saving = false; }
  }

  startEdit(customer: any) {
    this.editingCustomerId = customer.customer_id;
    this.showForm = true;
    this.formError = '';
    this.form.patchValue({
      name: customer.name ?? '',
      customer_type: customer.customer_type ?? 'EXTERNAL',
      email: customer.email ?? '',
      phone: customer.phone ?? '',
      address: customer.address ?? '',
    });
  }

  cancelForm() {
    this.showForm = false;
    this.editingCustomerId = null;
    this.formError = '';
    this.form.reset({ customer_type: 'EXTERNAL' });
  }

  async deleteCustomer(customer: any) {
    if (!confirm(`Delete customer "${customer.name}"?`)) return;
    try {
      await this.receivables.deleteCustomer(customer.customer_id);
      await this.load();
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? 'Failed to delete customer.';
    }
  }

  async exportFile(format: 'pdf' | 'xlsx') {
    try {
      await this.receivables.exportCustomers(format);
    } catch {
      this.error = 'Export failed.';
    }
  }
}
