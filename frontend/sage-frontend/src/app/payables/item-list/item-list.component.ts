import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { PayablesService } from '../../services/payables.service';
import { AccountsService } from '../../services/accounts.service';
import { AccountSelectComponent } from '../../shared/account-select/account-select.component';
import { VendorSelectComponent } from '../../shared/vendor-select/vendor-select.component';

@Component({
  selector: 'app-item-list',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterModule, AccountSelectComponent, VendorSelectComponent],
  templateUrl: './item-list.component.html',
})
export class ItemListComponent implements OnInit {
  items: any[] = [];
  vendors: any[] = [];
  allAccounts: any[] = [];
  loading = true;
  error = '';
  showForm = false;
  saving = false;
  formError = '';
  editingItemId: string | null = null;
  form!: FormGroup;

  constructor(
    private fb: FormBuilder,
    private payables: PayablesService,
    private accountsService: AccountsService,
  ) {}

  async ngOnInit() {
    this.initForm();
    try {
      const [itemsData, vendorsData, accountsData] = await Promise.all([
        this.payables.getItems(),
        this.payables.getVendors(),
        this.accountsService.getAll(),
      ]);
      this.items = itemsData.results ?? itemsData;
      this.vendors = vendorsData.results ?? vendorsData;
      this.allAccounts = accountsData.results ?? accountsData;
    } catch {
      this.error = 'Failed to load data.';
    } finally {
      this.loading = false;
    }
  }

  initForm() {
    this.form = this.fb.group({
      name: ['', Validators.required],
      item_type: ['SERVICE', Validators.required],
      description: [''],
      unit_price: [0, [Validators.required, Validators.min(0)]],
      vendor_id: [''],
      expense_account_id: [''],
      revenue_account_id: [''],
    });
  }

  startEdit(item: any) {
    this.editingItemId = item.item_id;
    this.formError = '';
    this.form.patchValue({
      name: item.name,
      item_type: item.item_type,
      description: item.description ?? '',
      unit_price: item.unit_price ?? 0,
      vendor_id: item.vendor_id ?? '',
      expense_account_id: item.expense_account_id ?? '',
      revenue_account_id: item.revenue_account_id ?? '',
    });
    this.showForm = true;
  }

  cancelForm() {
    this.showForm = false;
    this.editingItemId = null;
    this.formError = '';
    this.initForm();
  }

  async submit() {
    if (!this.form.valid || this.saving) return;
    this.saving = true;
    this.formError = '';
    try {
      const payload = { ...this.form.value };
      if (this.editingItemId) {
        const updated = await this.payables.updateItem(this.editingItemId, payload);
        const idx = this.items.findIndex(i => i.item_id === this.editingItemId);
        if (idx !== -1) this.items = [...this.items.slice(0, idx), updated, ...this.items.slice(idx + 1)];
      } else {
        const created = await this.payables.createItem(payload);
        this.items = [...this.items, created];
      }
      this.cancelForm();
    } catch (e: any) {
      this.formError = e.response?.data?.detail ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Save failed.');
    } finally {
      this.saving = false;
    }
  }

  async deleteItem(item: any) {
    if (!confirm(`Delete "${item.name}"?`)) return;
    try {
      await this.payables.deleteItem(item.item_id);
      this.items = this.items.filter(i => i.item_id !== item.item_id);
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? 'Delete failed.';
    }
  }
}
