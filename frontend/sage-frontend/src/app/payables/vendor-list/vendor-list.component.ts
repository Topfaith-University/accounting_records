import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { PayablesService } from '../../services/payables.service';

@Component({
  selector: 'app-vendor-list',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './vendor-list.component.html',
})
export class VendorListComponent implements OnInit {
  vendors: any[] = [];
  loading = true;
  error = '';
  showForm = false;
  saving = false;
  formError = '';
  form!: FormGroup;

  constructor(private payables: PayablesService, private fb: FormBuilder) {}

  async ngOnInit() {
    this.form = this.fb.group({
      name: ['', Validators.required],
      email: [''],
      phone: [''],
      address: [''],
    });
    await this.load();
  }

  async load() {
    this.loading = true;
    try {
      const data = await this.payables.getVendors();
      this.vendors = data.results ?? data;
    } catch { this.error = 'Failed to load vendors.'; }
    finally { this.loading = false; }
  }

  async submit() {
    if (!this.form.valid) return;
    this.saving = true;
    this.formError = '';
    try {
      await this.payables.createVendor(this.form.value);
      this.form.reset();
      this.showForm = false;
      await this.load();
    } catch (e: any) {
      this.formError = e.response?.data?.detail ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Save failed.');
    } finally { this.saving = false; }
  }
}
