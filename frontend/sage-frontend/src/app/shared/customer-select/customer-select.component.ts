import {
  Component, Input, Output, EventEmitter, OnInit,
  HostListener, ElementRef, forwardRef
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, NG_VALUE_ACCESSOR, ControlValueAccessor } from '@angular/forms';
import { ReceivablesService } from '../../services/receivables.service';

interface Customer {
  customer_id: string;
  name: string;
  customer_type?: string;
  email?: string;
}

@Component({
  selector: 'app-customer-select',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './customer-select.component.html',
  providers: [{
    provide: NG_VALUE_ACCESSOR,
    useExisting: forwardRef(() => CustomerSelectComponent),
    multi: true,
  }],
})
export class CustomerSelectComponent implements OnInit, ControlValueAccessor {
  @Input() placeholder = 'Search or create customer…';
  @Input() allCustomers: Customer[] = [];

  @Output() customersChanged = new EventEmitter<Customer[]>();

  searchText = '';
  showDropdown = false;
  showModal = false;
  filteredCustomers: Customer[] = [];

  newCustomer = { name: '', customer_type: 'EXTERNAL', email: '', phone: '' };
  creatingCustomer = false;
  createError = '';

  selectedCustomer: Customer | null = null;

  private onChange: (val: string) => void = () => {};
  private onTouched: () => void = () => {};

  constructor(
    private receivablesService: ReceivablesService,
    private elRef: ElementRef,
  ) {}

  async ngOnInit() {
    if (this.allCustomers.length === 0) {
      try {
        const data = await this.receivablesService.getCustomers();
        this.allCustomers = data.results ?? data;
      } catch {}
    }
    this.filteredCustomers = [...this.allCustomers];
  }

  writeValue(id: string) {
    const found = this.allCustomers.find(c => c.customer_id === id) ?? null;
    this.selectedCustomer = found;
    this.searchText = found ? found.name : '';
  }

  registerOnChange(fn: (val: string) => void) { this.onChange = fn; }
  registerOnTouched(fn: () => void) { this.onTouched = fn; }

  onInput() {
    this.showDropdown = true;
    const q = this.searchText.toLowerCase();
    this.filteredCustomers = this.allCustomers.filter(
      c => c.name.toLowerCase().includes(q) || (c.email ?? '').toLowerCase().includes(q)
    );
    if (!this.filteredCustomers.find(c => c.name === this.searchText)) {
      this.selectedCustomer = null;
      this.onChange('');
    }
  }

  selectCustomer(customer: Customer) {
    this.selectedCustomer = customer;
    this.searchText = customer.name;
    this.showDropdown = false;
    this.onChange(customer.customer_id);
    this.onTouched();
  }

  openCreateModal() {
    this.showDropdown = false;
    this.newCustomer = { name: this.searchText.trim(), customer_type: 'EXTERNAL', email: '', phone: '' };
    this.createError = '';
    this.showModal = true;
  }

  async createAndSelect() {
    if (!this.newCustomer.name) return;
    this.creatingCustomer = true;
    this.createError = '';
    try {
      const created: Customer = await this.receivablesService.createCustomer(this.newCustomer);
      this.allCustomers = [...this.allCustomers, created];
      this.filteredCustomers = [...this.allCustomers];
      this.customersChanged.emit(this.allCustomers);
      this.selectCustomer(created);
      this.showModal = false;
    } catch (e: any) {
      this.createError = e.response?.data?.detail
        ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Failed to create customer.');
    } finally {
      this.creatingCustomer = false;
    }
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent) {
    if (!this.elRef.nativeElement.contains(event.target)) {
      this.showDropdown = false;
    }
  }
}
