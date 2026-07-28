import {
  Component, Input, Output, EventEmitter, OnInit,
  HostListener, ElementRef, forwardRef
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, NG_VALUE_ACCESSOR, ControlValueAccessor } from '@angular/forms';
import { PayablesService } from '../../services/payables.service';

interface Vendor {
  vendor_id: string;
  name: string;
  email?: string;
  phone?: string;
}

@Component({
  selector: 'app-vendor-select',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './vendor-select.component.html',
  providers: [{
    provide: NG_VALUE_ACCESSOR,
    useExisting: forwardRef(() => VendorSelectComponent),
    multi: true,
  }],
})
export class VendorSelectComponent implements OnInit, ControlValueAccessor {
  @Input() placeholder = 'Search or create vendor…';
  @Input() allVendors: Vendor[] = [];

  @Output() vendorsChanged = new EventEmitter<Vendor[]>();

  searchText = '';
  showDropdown = false;
  showModal = false;
  filteredVendors: Vendor[] = [];

  newVendor = { name: '', email: '', phone: '', address: '' };
  creatingVendor = false;
  createError = '';

  selectedVendor: Vendor | null = null;

  private onChange: (val: string) => void = () => {};
  private onTouched: () => void = () => {};

  constructor(
    private payablesService: PayablesService,
    private elRef: ElementRef,
  ) {}

  async ngOnInit() {
    if (this.allVendors.length === 0) {
      try {
        const data = await this.payablesService.getVendors();
        this.allVendors = data.results ?? data;
      } catch {}
    }
    this.filteredVendors = [...this.allVendors];
  }

  writeValue(id: string) {
    const found = this.allVendors.find(v => v.vendor_id === id) ?? null;
    this.selectedVendor = found;
    this.searchText = found ? found.name : '';
  }

  registerOnChange(fn: (val: string) => void) { this.onChange = fn; }
  registerOnTouched(fn: () => void) { this.onTouched = fn; }

  onInput() {
    this.showDropdown = true;
    const q = this.searchText.toLowerCase();
    this.filteredVendors = this.allVendors.filter(
      v => v.name.toLowerCase().includes(q) || (v.email ?? '').toLowerCase().includes(q)
    );
    if (!this.filteredVendors.find(v => v.name === this.searchText)) {
      this.selectedVendor = null;
      this.onChange('');
    }
  }

  selectVendor(vendor: Vendor) {
    this.selectedVendor = vendor;
    this.searchText = vendor.name;
    this.showDropdown = false;
    this.onChange(vendor.vendor_id);
    this.onTouched();
  }

  openCreateModal() {
    this.showDropdown = false;
    this.newVendor = { name: this.searchText.trim(), email: '', phone: '', address: '' };
    this.createError = '';
    this.showModal = true;
  }

  async createAndSelect() {
    if (!this.newVendor.name) return;
    this.creatingVendor = true;
    this.createError = '';
    try {
      const created: Vendor = await this.payablesService.createVendor(this.newVendor);
      this.allVendors = [...this.allVendors, created];
      this.filteredVendors = [...this.allVendors];
      this.vendorsChanged.emit(this.allVendors);
      this.selectVendor(created);
      this.showModal = false;
    } catch (e: any) {
      this.createError = e.response?.data?.detail
        ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Failed to create vendor.');
    } finally {
      this.creatingVendor = false;
    }
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent) {
    if (!this.elRef.nativeElement.contains(event.target)) {
      this.showDropdown = false;
    }
  }
}
